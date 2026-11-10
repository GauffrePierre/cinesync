"""Habitudes de visionnage tirées de l'historique : selon le jour de la semaine, plutôt des épisodes ou des films ?
Et séries commencées presque finies. Sert à « Pour ce soir »."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import WatchEvent
from app.services.clock import utcnow
from app.services.context import Ctx
from app.services.errors import ServiceError

MIN_EVENINGS = 4  # soirées de ce jour de la semaine nécessaires pour parler d'habitude


def evening_habit(ctx: Ctx, weekday: int, tz_offset_min: int = 0) -> dict | None:
    """Pour ce jour de la semaine (0 = lundi) : part des soirées avec des épisodes plutôt que des films, sur un an.
    {"prefer": "tv" | "movie", "share_tv", "evenings"}, ou None sans habitude nette (ou trop peu de données)."""
    since = utcnow() - timedelta(days=365)
    tz = timedelta(minutes=tz_offset_min)
    kinds: dict = defaultdict(set)  # date locale -> types regardés ce jour-là
    for kind, at in ctx.db.execute(
        select(WatchEvent.kind, WatchEvent.watched_at).where(WatchEvent.watched_at >= since, WatchEvent.approx_date.is_(False))
    ).all():
        local = at + tz
        if local.weekday() == weekday:
            kinds[local.date()].add("tv" if kind == "episode" else "movie")
    evenings = len(kinds)
    if evenings < MIN_EVENINGS:
        return None
    tv = sum(1 for k in kinds.values() if "tv" in k and "movie" not in k)
    movie = sum(1 for k in kinds.values() if "movie" in k and "tv" not in k)
    if tv + movie == 0:
        return None
    share = tv / (tv + movie)
    prefer = "tv" if share >= 0.65 else "movie" if share <= 0.35 else None
    return {"prefer": prefer, "share_tv": round(share, 2), "evenings": evenings} if prefer else None


async def nearly_finished(ctx: Ctx, max_remaining: int = 8, limit: int = 20) -> list[dict]:
    """Séries commencées (historique de l'année) dont il reste peu d'épisodes sortis à voir : [{tmdb_id, remaining}]."""
    since = utcnow() - timedelta(days=365)
    watched: dict[int, set] = defaultdict(set)
    last: dict[int, datetime] = {}
    for tid, s, e, at in ctx.db.execute(
        select(WatchEvent.tmdb_id, WatchEvent.season, WatchEvent.episode, WatchEvent.watched_at)
        .where(WatchEvent.kind == "episode", WatchEvent.tmdb_id.isnot(None), WatchEvent.watched_at >= since)
    ).all():
        if s and e:  # saison 0 (épisodes spéciaux) ignorée
            watched[tid].add((s, e))
            last[tid] = max(last.get(tid, at), at)
    out = []
    for tid in sorted(watched, key=lambda t: last[t], reverse=True)[:limit * 2]:
        try:
            raw = await ctx.tmdb._get(f"/tv/{tid}", ttl=21600)
        except ServiceError:
            continue
        aired_last = raw.get("last_episode_to_air") or {}
        ls, le = aired_last.get("season_number") or 0, aired_last.get("episode_number") or 0
        aired = {(s["season_number"], n) for s in raw.get("seasons") or [] if 0 < (s.get("season_number") or 0) < ls
                 for n in range(1, (s.get("episode_count") or 0) + 1)}
        aired |= {(ls, n) for n in range(1, le + 1)} if ls else set()
        remaining = len(aired - watched[tid])
        if 0 < remaining <= max_remaining:
            out.append({"tmdb_id": tid, "remaining": remaining})
        if len(out) >= limit:
            break
    return out
