"""Moteur de suggestions : likes du mode swipe + historique/notes Trakt + recommandations TMDB."""

import asyncio
import logging
import random

from sqlalchemy import select

from app.models import MediaState, SwipeHistory
from app.services.context import Ctx
from app.services.enrich import enrich, refs_to_items
from app.services.errors import ServiceError

log = logging.getLogger(__name__)


async def _safe(coro, default):
    try:
        return await coro
    except ServiceError as e:
        log.info("suggestions: %s", e.message)
        return default


def swipe_keys(ctx: Ctx, actions: tuple[str, ...] | None = None) -> set[tuple[str, int]]:
    q = select(SwipeHistory.media_type, SwipeHistory.tmdb_id)
    if actions:
        q = q.where(SwipeHistory.action.in_(actions))
    return {(mt, tid) for mt, tid in ctx.db.execute(q).all()}


async def excluded_keys(ctx: Ctx) -> set[tuple[str, int]]:
    """Titres à ne jamais proposer : déjà swipés, déjà vus ou déjà en watchlist (tous services)."""
    keys = swipe_keys(ctx)
    for r in ctx.db.execute(select(MediaState)).scalars():
        if r.in_watchlist or r.watched or r.disliked:
            keys.add((r.media_type, r.tmdb_id))
    if ctx.trakt:
        keys |= await _safe(ctx.trakt.watched_keys(), set())
    return keys


async def seeds(ctx: Ctx, media_types: list[str]) -> list[dict]:
    """Titres « graines » : ce que tu as aimé récemment."""
    rows = ctx.db.execute(
        select(SwipeHistory)
        .where(SwipeHistory.action.in_(("like", "watchlist")), SwipeHistory.media_type.in_(media_types))
        .order_by(SwipeHistory.created_at.desc())
        .limit(8)
    ).scalars()
    out = [{"media_type": r.media_type, "tmdb_id": r.tmdb_id, "title": r.title, "weight": 1.5 if r.action == "like" else 1.0} for r in rows]

    if ctx.trakt:
        ratings, history = await asyncio.gather(_safe(ctx.trakt.ratings(), []), _safe(ctx.trakt.history(20), []))
        out += [{**r, "weight": 1.3} for r in ratings if (r.get("rating") or 0) >= 8 and r["media_type"] in media_types][:6]
        out += [{**h, "weight": 0.8} for h in history if h["media_type"] in media_types][:6]

    seen, uniq = set(), []
    for s in out:
        k = (s["media_type"], s["tmdb_id"])
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return uniq[:10]


async def suggestions(ctx: Ctx, media_type: str = "all", limit: int = 20, with_enrich: bool = True) -> list[dict]:
    media_types = ["movie", "tv"] if media_type == "all" else [media_type]
    excluded, seed_list = await asyncio.gather(excluded_keys(ctx), seeds(ctx, media_types))
    excluded |= {(s["media_type"], s["tmdb_id"]) for s in seed_list}

    scores: dict[tuple[str, int], float] = {}
    items: dict[tuple[str, int], dict] = {}

    def add(item: dict, score: float, reason: str) -> None:
        k = (item["media_type"], item["id"])
        if k in excluded:
            return
        if k not in items:
            items[k] = {**item, "reason": reason}
        scores[k] = scores.get(k, 0) + score

    # 1. Recommandations TMDB à partir des graines
    rec_lists = await asyncio.gather(
        *(_safe(ctx.tmdb.recommendations(s["media_type"], s["tmdb_id"]), []) for s in seed_list)
    )
    for s, recs in zip(seed_list, rec_lists):
        for rank, item in enumerate(recs[:15]):
            add(item, s["weight"] * (15 - rank) / 15, f"Parce que tu as aimé {s['title']}" if s.get("title") else "Pour toi")

    # 2. Recommandations personnalisées Trakt
    if ctx.trakt:
        trakt_refs = []
        for mt in media_types:
            trakt_refs += await _safe(ctx.trakt.recommendations(mt, 15), [])
        trakt_refs = [r for r in trakt_refs if (r["media_type"], r["tmdb_id"]) not in excluded][:12]
        for item in await refs_to_items(ctx, trakt_refs):
            add(item, 1.2, "Recommandé par Trakt")

    # 3. Complément : incontournables bien notés
    if len(items) < limit:
        for mt in media_types:
            extra = await _safe(
                ctx.tmdb.discover(mt, page=random.randint(1, 5), sort_by="vote_average.desc", **{"vote_count.gte": 1500}),
                [],
            )
            for item in extra:
                add(item, 0.1, "Incontournable")

    # Genres des titres « pas intéressé » : pénalité proportionnelle (2 rejets d'un genre ou plus)
    disliked_rows = list(ctx.db.execute(select(MediaState).where(MediaState.disliked.is_(True))).scalars())[:40]
    if disliked_rows and not ctx.tmdb.is_mock:
        from collections import Counter

        basics = await asyncio.gather(*(_safe(ctx.tmdb.basic(r.media_type, r.tmdb_id), None) for r in disliked_rows))
        bad = Counter(g for b in basics if b for g in b.get("genre_ids", []))
        for k, it in items.items():
            penalty = sum(bad[g] for g in it.get("genre_ids", []) if bad[g] >= 2)
            if penalty:
                scores[k] /= 1 + 0.25 * penalty

    ranked = sorted(items, key=lambda k: scores[k], reverse=True)[:limit]
    result = [items[k] for k in ranked]
    return await enrich(ctx, result) if with_enrich else result
