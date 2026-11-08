"""Tâches périodiques.

- Collecte de l'état personnel depuis tous les services : toutes les 30 min.
- Disponibilités de la watchlist (Trakt + Plex) sur tes plateformes : toutes les 24 h (notifications).
- Santé des services : toutes les 15 min.
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
from app.services.errors import ServiceError

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


async def availability_one(ctx: Ctx) -> dict:
    db = ctx.db
    if ctx.tmdb.is_mock:
        return {"checked": 0, "created": 0, "skipped": "TMDB doit être configuré"}
    if not ctx.settings.notify_availability:
        return {"checked": 0, "created": 0, "skipped": "Notifications de disponibilité désactivées"}
    platforms = set(ctx.platforms)
    if not platforms:
        return {"checked": 0, "created": 0, "skipped": "Aucune plateforme active"}

    rows = [r for r in db.execute(select(MediaState)).scalars() if r.in_watchlist]
    created = 0
    for r in rows:
        try:
            prov = stream_providers(await ctx.tmdb.providers(r.media_type, r.tmdb_id, fresh=True))
        except ServiceError:
            continue
        # Repère propre à cette vérification (la page Watchlist remplit aussi providers_checked_at)
        first_check = r.availability_checked_at is None
        r.providers = json.dumps(prov)
        r.providers_checked_at = r.availability_checked_at = datetime.utcnow()
        available = {p["id"]: p for p in prov if p["id"] in platforms}
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
                    message=f"{title} est maintenant disponible sur {', '.join(names)}",
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
    recent = datetime.utcnow() - timedelta(days=180)
    shows |= {t for (t,) in db.execute(select(WatchEvent.tmdb_id).where(WatchEvent.kind == "episode", WatchEvent.watched_at >= recent, WatchEvent.tmdb_id.isnot(None)))}
    cutoff = (date.today() - timedelta(days=2)).isoformat()
    created = 0
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
        message = f"Nouvel épisode de {title} : {code}" + (f" · {last['name']}" if last.get("name") else "")
        exists = db.execute(select(Notification.id).where(Notification.kind == "episode", Notification.tmdb_id == tmdb_id, Notification.message == message)).first()
        if exists:
            continue
        poster = f"https://image.tmdb.org/t/p/w342{raw['poster_path']}" if raw.get("poster_path") else None
        db.add(Notification(kind="episode", tmdb_id=tmdb_id, media_type="tv", title=title, poster=poster, message=message))
        created += 1
    db.commit()
    return {"checked": len(shows), "created": created}


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
    ]
    for func, interval, first, job_id in jobs:
        scheduler.add_job(func, "interval", **interval, next_run_time=first, id=job_id, replace_existing=True, max_instances=1, coalesce=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
