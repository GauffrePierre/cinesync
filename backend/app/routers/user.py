"""Réglages, état des connexions, tests de connexion, statistiques."""

import asyncio
import json
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.models import SwipeHistory
from app.schemas.settings import SECRET_FIELDS, SettingsOut, SettingsUpdate, TestResult
from app.services.cache import cache
from app.routers.jellyfin import status_for as jellyfin_status
from app.services.context import GLOBAL_FIELDS, SHARED_ID, Ctx, get_ctx
from app.services import health, history
from app.services.errors import ServiceError

router = APIRouter(tags=["user"])

_background: set[asyncio.Task] = set()  # garde une référence aux tâches lancées

FALLBACK_COUNTRIES = [
    ("CH", "Suisse"), ("FR", "France"), ("BE", "Belgique"), ("LU", "Luxembourg"), ("CA", "Canada"),
    ("DE", "Allemagne"), ("AT", "Autriche"), ("IT", "Italie"), ("ES", "Espagne"), ("PT", "Portugal"),
    ("NL", "Pays-Bas"), ("GB", "Royaume-Uni"), ("IE", "Irlande"), ("US", "États-Unis"), ("SE", "Suède"),
    ("NO", "Norvège"), ("DK", "Danemark"), ("FI", "Finlande"), ("JP", "Japon"), ("AU", "Australie"),
]


@router.get("/settings", response_model=SettingsOut)
def get_settings(ctx: Ctx = Depends(get_ctx)):
    return SettingsOut.from_model(ctx.settings, admin=ctx.server_admin, has_plex=ctx.server_admin or ctx.plex is not None)


# Réglages du serveur modifiables par l'admin seulement (plex_token : jeton saisi à la main pour le serveur)
ADMIN_FIELDS = GLOBAL_FIELDS | {"plex_token"}


@router.put("/settings", response_model=SettingsOut)
async def update_settings(body: SettingsUpdate, ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings
    data = body.model_dump(exclude_unset=True)
    if not ctx.server_admin and (forbidden := sorted(f for f, v in data.items() if f in ADMIN_FIELDS and v is not None)):
        raise HTTPException(403, "Réglages réservés à l'administrateur : " + ", ".join(forbidden))
    if data.get("admins_full_access") is not None and ctx.user.id != SHARED_ID:
        raise HTTPException(403, "Seul le compte administrateur principal peut modifier ce réglage")
    old_trakt_app = s.trakt_client_id
    for field, value in data.items():
        if value is None:
            continue
        if field in SECRET_FIELDS and isinstance(value, str) and value.startswith("••••"):
            continue  # aperçu masqué renvoyé tel quel : ne pas écraser
        if field == "active_platforms":
            s.platforms = value
        elif field == "cinemas":
            s.cinemas = json.dumps([{k: c.get(k) for k in ("id", "name", "city", "country")} for c in value if c.get("id")])
        elif field == "country_code":
            s.country_code = value.upper()
        elif field in ("notify_episode_via", "notify_movie_via", "notify_episode_when", "family_kids"):
            setattr(s, field, json.dumps(sorted(set(value))))
        elif field == "nav_order":
            s.nav_order = json.dumps(list(dict.fromkeys(value)))  # sans doublons
        elif isinstance(value, str):
            setattr(s, field, value.strip().rstrip("/") if field.endswith("_url") else value.strip())
        else:
            setattr(s, field, value)
    # Changer d'application Trakt invalide la session existante
    if s.trakt_client_id != old_trakt_app:
        s.trakt_access_token = s.trakt_refresh_token = s.trakt_username = ""
        s.trakt_token_expires_at = None
    ctx.db.commit()
    if ctx.server_admin and any(f in GLOBAL_FIELDS and v is not None for f, v in data.items()):
        cache.clear()  # réglage du serveur modifié (un champ du serveur envoyé vide par un membre est ignoré)
    # Revérifie aussitôt les services en arrière-plan (sidebar et alertes à jour)
    _background.add(task := asyncio.create_task(health.check_all([ctx.user.id])))
    task.add_done_callback(_background.discard)
    return SettingsOut.from_model(s, admin=ctx.server_admin, has_plex=ctx.server_admin or ctx.plex is not None)


@router.get("/settings/status")
def connection_status(ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings
    return {
        "tmdb": {"configured": bool(s.tmdb_api_key), "mock": not s.tmdb_api_key},
        # Rien du Plex du serveur pour un membre qui n'y est pas relié (ni le nom du serveur)
        "plex": {"configured": ctx.plex is not None, "server": (s.plex_server_name or None) if ctx.plex else None,
                 "account": bool(s.plex_account_token), "own": ctx.plex_own is not None},
        "jellyfin": jellyfin_status(ctx),
        # Bibliothèque du compte (Plex, sinon Jellyfin / Emby) : onglet Bibliothèque, badges, liens « Lire »
        "media": {"configured": ctx.media is not None, "server": ("plex" if ctx.plex else (s.jellyfin_kind or "jellyfin")) if ctx.media else None},
        "trakt": {"configured": bool(s.trakt_client_id), "connected": bool(s.trakt_access_token), "username": s.trakt_username or None},
        "seerr": {"configured": bool(s.seerr_url and s.seerr_api_key)},
        "letterboxd": {"configured": bool(s.letterboxd_username), "username": s.letterboxd_username or None},
        "justwatch": {"configured": s.justwatch_enabled},
        "cinema": {"configured": bool(s.cinema_list), "cinemas": s.cinema_list},
        "country": s.country_code,
        "platforms": s.platforms,
        # Services utilisés et leur santé (None = pas encore vérifié) — sidebar
        # Seerr renseigne sur la bibliothèque du serveur : rien pour un membre qui n'y est pas relié
        "health": {k: v for k, v in health.state_for(s, ctx.user.id).items() if k != "seerr" or ctx.is_admin or ctx.seerr is not None},
    }


@router.post("/settings/test/{service}", response_model=TestResult)
async def test_connection(service: str, ctx: Ctx = Depends(get_ctx)):
    if service not in health.SERVICES:
        raise HTTPException(404, f"Service inconnu : {service}")
    if service == "seerr" and not ctx.is_admin and ctx.seerr is None:
        raise HTTPException(403, "Les demandes d'ajout sont réservées aux comptes reliés au serveur multimédia")
    result = await health.test_service(ctx, service)
    # Service du serveur testé par un membre (avec son propre accès) : pas d'effet sur l'état commun
    if service in health.used_services(ctx.settings) and (service not in health.GLOBAL_SERVICES or ctx.user.id == SHARED_ID):
        health.record(ctx.db, service, result, ctx.user.id)
    if not ctx.server_admin and service in health.GLOBAL_SERVICES:
        result = {**result, "details": None}  # détails du serveur (comptes, versions) : admin seulement
    return TestResult(**result)


@router.get("/meta/countries")
async def countries(ctx: Ctx = Depends(get_ctx)):
    if not ctx.tmdb.is_mock:
        try:
            regions = await ctx.tmdb.regions()
            if regions:
                return regions
        except ServiceError:
            pass
    return [{"code": c, "name": n} for c, n in FALLBACK_COUNTRIES]


@router.get("/meta/providers")
async def providers_catalog(ctx: Ctx = Depends(get_ctx)):
    """Plateformes disponibles dans le pays configuré (films + séries), triées par popularité."""
    try:
        movie, tv = await asyncio.gather(ctx.tmdb.provider_catalog("movie"), ctx.tmdb.provider_catalog("tv"))
    except ServiceError as e:
        raise HTTPException(e.status, e.message) from e
    merged: dict[int, dict] = {}
    for p in movie + tv:
        if p["id"] not in merged or p["priority"] < merged[p["id"]]["priority"]:
            merged[p["id"]] = p
    return {"results": sorted(merged.values(), key=lambda p: p["priority"]), "mock": ctx.tmdb.is_mock}


@router.get("/stats/activity")
async def stats_activity(
    period: str = "week", offset: int = Query(0, ge=0, le=5000), tz: int = Query(0, ge=-900, le=900), ctx: Ctx = Depends(get_ctx)
):
    """Statistiques détaillées. period : day | week | month | year ; offset : fenêtres vers le passé ;
    tz : décalage du fuseau du navigateur en minutes (pour couper les journées à minuit local)."""
    if period not in history.PERIODS:
        raise HTTPException(422, "period doit être day, week, month ou year")
    from sqlalchemy import func as f

    from app.models import WatchEvent

    out = history.stats(ctx.db, period, max(0, offset), tz_offset_min=tz)
    if not ctx.db.execute(select(f.count()).select_from(WatchEvent)).scalar():
        out["needs_import"] = True  # premier affichage : l'interface lance l'import (POST /stats/import)
    return out


@router.get("/stats/events")
def stats_events(start: str = Query(max_length=40), end: str = Query(max_length=40), tz: int = Query(0, ge=-900, le=900), ctx: Ctx = Depends(get_ctx)):
    try:
        return {"results": history.events_between(ctx.db, start, end, tz_offset_min=tz)}
    except ValueError as e:
        raise HTTPException(422, "Dates invalides") from e


@router.post("/stats/import")
async def stats_import(ctx: Ctx = Depends(get_ctx)):
    return await history.import_all(ctx)


@router.get("/stats")
async def stats(ctx: Ctx = Depends(get_ctx)):
    swipes = dict(ctx.db.execute(select(SwipeHistory.action, func.count()).group_by(SwipeHistory.action)).all())
    out: dict = {"swipe": swipes, "watched": None, "plex": None, "letterboxd": None}

    def watched_totals():
        """Films vus, séries suivies, épisodes et heures, d'après tout ce que SynCiné garde (historique de toutes les
        sources : Trakt, Plex, Jellyfin, Letterboxd, et titres marqués vus) : les mêmes chiffres que la page Statistiques."""
        from app.models import MediaState, WatchEvent

        movies, shows, episodes, minutes = set(), set(), set(), 0
        for kind, tid, title, show, season, episode, runtime in ctx.db.execute(
            select(WatchEvent.kind, WatchEvent.tmdb_id, WatchEvent.title, WatchEvent.show_title, WatchEvent.season, WatchEvent.episode,
                   WatchEvent.runtime_min)
        ).all():
            minutes += runtime or 0
            if kind == "movie":
                movies.add(tid or title)
            else:
                shows.add(tid or show)
                episodes.add((tid or show, season, episode))
        for mt, tid in ctx.db.execute(select(MediaState.media_type, MediaState.tmdb_id).where(MediaState.watched_sources != "[]")).all():
            (movies if mt == "movie" else shows).add(tid)
        out["watched"] = {"movies_watched": len(movies), "shows_watched": len(shows), "episodes_watched": len(episodes),
                          "hours": round(minutes / 60)}

    async def plex_stats():
        # Bibliothèque du serveur multimédia (Plex, sinon Jellyfin / Emby) ; clé « plex » gardée pour l'interface
        if not ctx.media:
            return
        lib = await ctx.media.library()
        c = Counter(i["media_type"] for i in lib)
        out["plex"] = {"movies": c.get("movie", 0), "shows": c.get("tv", 0), "server": "plex" if ctx.plex else ctx.media.kind,
                       "watched_movies": sum(1 for i in lib if i["media_type"] == "movie" and i.get("view_count"))}

    async def lb_stats():
        if not ctx.letterboxd:
            return
        d = await ctx.letterboxd.diary()
        out["letterboxd"] = {"recent_entries": len(d)}

    async def safe(coro):
        try:
            await coro
        except ServiceError:
            pass

    watched_totals()
    await asyncio.gather(safe(plex_stats()), safe(lb_stats()))
    return out
