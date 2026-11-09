"""Tris communs (Bibliothèque, Watchlist, Pour ce soir) et infos de tri des titres de la watchlist.

Champs attendus sur chaque titre : added (ISO), release_date (AAAA-MM-JJ), title, year, vote_average (note
globale /10), critic_score et audience_score (/100), personal_rating (/10). Une valeur absente passe en fin
de liste, quel que soit le sens du tri.
"""

import asyncio
import logging
from datetime import timedelta
from typing import Literal

from app.services.errors import ServiceError
from app.services.clock import utcnow

log = logging.getLogger(__name__)

Sort = Literal["added", "release", "title", "year", "rating", "critics", "audience", "personal"]

# Champ, et tri décroissant (le plus récent / le mieux noté d'abord) ou non
_FIELDS: dict[str, tuple[str, bool]] = {
    "added": ("added", True),
    "release": ("release_date", True),
    "title": ("title", False),
    "year": ("year", True),
    "rating": ("vote_average", True),
    "critics": ("critic_score", True),
    "audience": ("audience_score", True),
    "personal": ("personal_rating", True),
}


def sort_items(items: list[dict], sort: str) -> list[dict]:
    field, desc = _FIELDS.get(sort, _FIELDS["added"])

    def value(i):
        v = i.get(field)
        if field == "title":
            v = (v or "").lower() or None
        return None if v in (None, "", 0) and field != "title" else v

    present = [i for i in items if value(i) is not None]
    missing = [i for i in items if value(i) is None]
    present.sort(key=value, reverse=desc)
    return present + missing


# --- Infos de tri de la watchlist (stockées dans MediaState) ----------------------------

INFO_TTL = timedelta(days=7)


def _scores(s: dict) -> tuple[int | None, int | None]:
    critic = s.get("rt_critic")
    audience = s.get("rt_audience") or (round(s["imdb"] * 10) if s.get("imdb") else None)
    return critic, audience


async def fill_info(ctx, rows, limit: int = 150, scores: bool = True) -> int:
    """Complète sortie / note TMDB (et notes critique / public si le compte a Plex) des titres à rafraîchir.

    scores=False : seulement TMDB, sans marquer le titre comme à jour (la tâche périodique fera le reste)."""
    now = utcnow()
    todo = [r for r in rows if r.info_checked_at is None or now - r.info_checked_at > INFO_TTL] if scores else [
        r for r in rows if r.tmdb_rating is None and r.release_date is None and r.info_checked_at is None
    ]
    todo = todo[:limit]
    if not todo or ctx.tmdb.is_mock:
        return 0
    account = ctx.plex_account if scores else None
    plex_sem = asyncio.Semaphore(4)  # plex.tv : peu de requêtes à la fois

    async def one(r) -> None:
        try:
            item = await ctx.tmdb.basic(r.media_type, r.tmdb_id)
        except ServiceError:
            item = None
        if item:
            r.release_date, r.tmdb_rating = item.get("release_date"), item.get("vote_average") or None
            r.year = r.year or item.get("year")
        if account:
            try:
                async with plex_sem:
                    r.critic_score, r.audience_score = _scores(await account.scores(r.media_type, r.tmdb_id))
            except ServiceError:
                pass
        if scores:
            r.info_checked_at = now

    await asyncio.gather(*(one(r) for r in todo))
    ctx.db.commit()
    return len(todo)
