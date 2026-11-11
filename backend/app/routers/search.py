"""Recherche globale : TMDB + bibliothèque Plex + watchlist Trakt, résultats groupés par source."""

import asyncio

from fastapi import APIRouter, Depends, Query

from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich, refs_to_items
from app.services.errors import ServiceError

router = APIRouter(tags=["search"])


@router.get("/search")
async def global_search(q: str = Query(..., min_length=1, max_length=200), ctx: Ctx = Depends(get_ctx)):
    errors: dict[str, str] = {}
    ql = q.lower().strip()

    async def tmdb():
        items = (await ctx.tmdb.search_multi(q))[:18]
        return await enrich(ctx, items, providers=False)

    async def plex():
        return await ctx.plex.search(q, 12) if ctx.plex else []

    async def watchlist():
        if not ctx.trakt:
            return []
        refs = [r for r in await ctx.trakt.watchlist() if ql in (r.get("title") or "").lower()]
        return await refs_to_items(ctx, refs[:12])

    async def safe(name, coro):
        try:
            return await coro
        except ServiceError as e:
            errors[name] = e.message
            return []

    t, p, w = await asyncio.gather(safe("tmdb", tmdb()), safe("plex", plex()), safe("trakt", watchlist()))
    return {
        "query": q,
        "tmdb": t,
        "plex": p,
        "watchlist": w,
        "configured": {"plex": ctx.plex is not None, "trakt": ctx.trakt is not None},
        "errors": errors,
        "mock": ctx.tmdb.is_mock,
    }
