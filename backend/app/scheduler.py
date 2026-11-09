"""Tâches périodiques.

- Collecte de l'état personnel depuis tous les services : toutes les 30 min.
- Disponibilités de la watchlist (Trakt + Plex) sur tes plateformes : toutes les 24 h (notifications).
- Santé des services : toutes les 15 min.
- Sorties récentes des watchlists (Découvrir) : toutes les 3 h.
- Sauvegarde de la base : une par jour (vérifiée toutes les heures), si l'admin l'a activée.

Chaque tâche personnelle tourne pour chaque compte actif, dans une session liée à ce compte
(ses lignes seulement — voir UserScoped). Un compte en échec n'empêche pas les suivants.
"""

import json
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import config
from app.database import SessionLocal
from app.models import MediaState, Notification, User
from app.services.context import Ctx, ctx_for
from app.services.enrich import stream_providers
from app.services import messages
from app.services.errors import ServiceError
from app.services.clock import utcnow

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def _active_user_ids() -> list[int]:
    with SessionLocal() as db:
        # Les admins d'abord : l'historique Plex du serveur est importé par l'admin
        return [u.id for u in db.query(User).filter(User.active.is_(True)).order_by(User.role != "admin", User.id)]


async def for_each_user(job, user_ids: list[int] | None = None) -> dict:
    """Lance job(ctx) pour chaque compte actif (ou ceux donnés) ; résultat par id de compte."""
    out = {}
    for uid in user_ids or _active_user_ids():
        with SessionLocal() as db:
            user = db.get(User, uid)
            if user is None or not user.active:
                continue
            try:
                out[uid] = await job(ctx_for(db, user))
            except Exception as e:  # un compte en échec n'arrête pas les autres
                log.exception("Tâche %s (compte %s)", job.__name__, uid)
                db.rollback()
                out[uid] = {"error": e.__class__.__name__}
    return out


async def pull_one(ctx: Ctx) -> dict:
    from app.services.history import import_all
    from app.services.library_sync import pull

    result = await pull(ctx)
    result["history"] = await import_all(ctx)
    return result


async def pull_library() -> dict:
    return await for_each_user(pull_one)


async def check_watchlist_availability(user_ids: list[int] | None = None) -> dict:
    return await for_each_user(availability_one, user_ids)


async def check_new_episodes(user_ids: list[int] | None = None) -> dict:
    return await for_each_user(episodes_one, user_ids)


PLEX_ID = 0  # « plateforme » du serveur multimédia (Plex, Jellyfin, Emby) dans les disponibilités déjà notifiées


def _media(ctx: Ctx):
    """Serveur multimédia du compte (Plex, sinon Jellyfin / Emby) et son nom affiché ; (None, "") sans serveur."""
    media = getattr(ctx, "media", None)
    return (media, getattr(media, "label", "Plex")) if media is not None else (None, "")


async def availability_one(ctx: Ctx) -> dict:
    db = ctx.db
    if ctx.tmdb.is_mock:
        return {"checked": 0, "created": 0, "skipped": "TMDB doit être configuré"}
    if not ctx.settings.notify_availability:
        return {"checked": 0, "created": 0, "skipped": "Notifications de disponibilité désactivées"}
    via = set(ctx.settings.movie_via)
    platforms = set(ctx.platforms) if "platforms" in via else set()
    plex_index = {}
    media, server = _media(ctx)
    if "plex" in via and media is not None:  # valeur « plex » = le serveur multimédia, quel qu'il soit
        try:
            plex_index = await media.index()  # titres de la watchlist arrivés sur le serveur
        except ServiceError:
            plex_index = {}
    if not platforms and not plex_index:
        return {"checked": 0, "created": 0, "skipped": "Aucune plateforme active"}

    rows = [r for r in db.execute(select(MediaState)).scalars() if r.in_watchlist]
    created = 0
    for r in rows:
        try:
            prov = stream_providers(await ctx.tmdb.providers(r.media_type, r.tmdb_id, fresh=True)) if platforms else []
        except ServiceError:
            continue
        # Repère propre à cette vérification (la page Watchlist remplit aussi providers_checked_at)
        first_check = r.availability_checked_at is None
        if platforms:
            r.providers = json.dumps(prov)
            r.providers_checked_at = utcnow()
        r.availability_checked_at = utcnow()
        available = {p["id"]: p for p in prov if p["id"] in platforms}
        if (r.media_type, r.tmdb_id) in plex_index:
            available[PLEX_ID] = {"id": PLEX_ID, "name": server, "logo": None}  # serveur : identifiant réservé 0
        notified = {int(x) for x in json.loads(r.notified_platforms or "[]")}
        new_ids = set(available) - notified
        # Premier passage : on mémorise l'état sans notifier (le titre était peut-être déjà dispo)
        if new_ids and not first_check:
            names = [available[i]["name"] for i in new_ids]
            title = r.title or "Un titre de ta watchlist"
            db.add(
                Notification(
                    kind="availability",
                    tmdb_id=r.tmdb_id,
                    media_type=r.media_type,
                    title=title,
                    poster=r.poster,
                    **messages.fields("{title} est maintenant disponible sur {platforms}", title=title, platforms=", ".join(names)),
                    platforms=json.dumps([{"id": i, "name": available[i]["name"], "logo": available[i]["logo"]} for i in new_ids]),
                )
            )
            created += 1
        # État courant conservé : un titre qui quitte puis revient sur une plateforme est renotifié
        r.notified_platforms = json.dumps(sorted(available))
    db.commit()
    log.info("Disponibilités : %d titre(s) vérifié(s), %d alerte(s)", len(rows), created)
    return {"checked": len(rows), "created": created}


async def episodes_one(ctx: Ctx) -> dict:
    """Nouvel épisode diffusé (2 derniers jours) d'une série suivie : en watchlist, vue ou regardée récemment."""
    from datetime import date

    from app.models import WatchEvent

    db = ctx.db
    if ctx.tmdb.is_mock or not ctx.settings.notify_new_episodes:
        return {"checked": 0, "created": 0}
    shows = {r.tmdb_id for r in db.execute(select(MediaState).where(MediaState.media_type == "tv")).scalars() if r.in_watchlist or r.watched}
    recent = utcnow() - timedelta(days=180)
    shows |= {t for (t,) in db.execute(select(WatchEvent.tmdb_id).where(WatchEvent.kind == "episode", WatchEvent.watched_at >= recent, WatchEvent.tmdb_id.isnot(None)))}
    cutoff = (date.today() - timedelta(days=2)).isoformat()
    via = set(ctx.settings.episode_via)
    platforms = set(ctx.platforms)
    created = 0

    def notify(tmdb_id: int, raw: dict, text: dict) -> None:
        nonlocal created
        exists = db.execute(select(Notification.id).where(Notification.kind == "episode", Notification.tmdb_id == tmdb_id, Notification.message == text["message"])).first()
        if exists:
            return
        poster = f"https://image.tmdb.org/t/p/w342{raw['poster_path']}" if raw.get("poster_path") else None
        db.add(Notification(kind="episode", tmdb_id=tmdb_id, media_type="tv", title=raw.get("name") or "", poster=poster, **text))
        created += 1

    # Dès la diffusion, ou seulement si la série est sur une de mes plateformes
    if via & {"air", "platforms"}:
        for tmdb_id in list(shows)[:300]:
            try:
                raw = await ctx.tmdb._get(f"/tv/{tmdb_id}", ttl=21600)
            except ServiceError:
                continue
            last = raw.get("last_episode_to_air") or {}
            if not last.get("air_date") or last["air_date"] < cutoff:
                continue
            code = f"S{last.get('season_number', 0):02d}E{last.get('episode_number', 0):02d}"
            title = raw.get("name") or ""
            names = []
            if "platforms" in via and platforms:
                try:
                    names = [p["name"] for p in stream_providers(await ctx.tmdb.providers("tv", tmdb_id)) if p["id"] in platforms]
                except ServiceError:
                    names = []
            if names:
                text = messages.fields("Nouvel épisode de {title} sur {platforms} : {code}", title=title, platforms=", ".join(names), code=code)
            elif "air" not in via:
                continue  # pas sur mes plateformes : rien (l'utilisateur ne veut que ce qu'il peut regarder)
            elif last.get("name"):
                text = messages.fields("Nouvel épisode de {title} : {code} · {name}", title=title, code=code, name=last["name"])
            else:
                text = messages.fields("Nouvel épisode de {title} : {code}", title=title, code=code)
            notify(tmdb_id, raw, text)

    # Ajouté sur le serveur multimédia (épisodes arrivés ces 2 derniers jours)
    media, server = _media(ctx)
    if "plex" in via and media is not None:
        try:
            index, recent = await media.library(), await media.recent_episodes(days=2)
        except ServiceError:
            index, recent = [], []
        by_key = {str(i.get("rating_key")): i for i in index if i.get("media_type") == "tv" and i.get("id")}
        # Une notification par série : une saison ajoutée d'un coup donne « S01E01 → S01E10 »
        grouped: dict[str, list[tuple[int, int]]] = {}
        for ep in recent:
            show = by_key.get(ep["show_key"])
            if show and show["id"] in shows:
                grouped.setdefault(ep["show_key"], []).append((ep["season"] or 0, ep["episode"] or 0))
        for key, eps in grouped.items():
            show, eps = by_key[key], sorted(set(eps))
            first, last = (f"S{s_:02d}E{e:02d}" for s_, e in (eps[0], eps[-1]))
            code = first if len(eps) == 1 else f"{first} → {last}"
            raw = {"name": show.get("title") or "", "poster_path": None}
            notify(show["id"], raw, messages.fields("Nouvel épisode de {title} sur {platforms} : {code}", title=raw["name"], platforms=server, code=code))

    db.commit()
    return {"checked": len(shows), "created": created}


async def warm_releases() -> dict:
    """Sorties récentes des watchlists et infos de tri (notes, dates), calculées d'avance : Découvrir et les tris
s'affichent sans attendre TMDB ni plex.tv."""
    from app.services.suggestions import watchlist_releases

    from app.services.sorting import fill_info

    async def one(ctx: Ctx):
        n = len(await watchlist_releases(ctx, ctx.settings.recent_days or 0) or [])
        # Infos de tri de la watchlist (sortie, notes TMDB, critique et public), par lots de 150
        rows = [r for r in ctx.db.execute(select(MediaState)).scalars() if r.in_watchlist]
        return {"releases": n, "info": await fill_info(ctx, rows)}

    return await for_each_user(one)


async def daily_backup() -> dict | None:
    """Sauvegarde automatique de la base si la dernière date de plus de 23 h (réglages du serveur)."""
    import asyncio

    from app.services import backup
    from app.services.context import SHARED_ID, settings_for

    with SessionLocal() as db:
        shared = settings_for(db, SHARED_ID).shared
        enabled, keep = shared.backup_enabled, shared.backup_keep
    return await asyncio.to_thread(backup.run_automatic, enabled, keep)


def start_scheduler() -> None:
    from app.services.health import check_all

    now = datetime.now()
    jobs = [
        (check_all, {"minutes": 15}, now + timedelta(seconds=20), "services_health"),
        (pull_library, {"minutes": 30}, now + timedelta(seconds=45), "library_pull"),
        (check_watchlist_availability, {"hours": config.notification_interval_hours}, now + timedelta(minutes=5), "watchlist_availability"),
        (check_new_episodes, {"hours": 6}, now + timedelta(minutes=3), "new_episodes"),
        (daily_backup, {"hours": 1}, now + timedelta(minutes=10), "db_backup"),
        (warm_releases, {"hours": 3}, now + timedelta(minutes=2), "watchlist_releases"),
    ]
    for func, interval, first, job_id in jobs:
        scheduler.add_job(func, "interval", **interval, next_run_time=first, id=job_id, replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
