"""Endpoints TMDB : tendances, recherche, détails, Watch Providers, à venir."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich
from app.services.errors import ServiceError

router = APIRouter(prefix="/tmdb", tags=["tmdb"])

MediaType = Literal["movie", "tv"]


@router.get("/trending")
async def trending(
    media_type: Literal["all", "movie", "tv"] = "all",
    page: int = Query(1, ge=1, le=20),
    with_providers: bool = True,
    ctx: Ctx = Depends(get_ctx),
):
    items = await ctx.tmdb.trending(media_type, page)
    await enrich(ctx, items, providers=with_providers)
    return {"results": items, "page": page, "mock": ctx.tmdb.is_mock}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), page: int = 1, ctx: Ctx = Depends(get_ctx)):
    items = await ctx.tmdb.search_multi(q, page)
    await enrich(ctx, items, providers=False)
    return {"results": items, "page": page, "mock": ctx.tmdb.is_mock}


@router.get("/upcoming")
async def upcoming(
    media_type: Literal["all", "movie", "tv"] = "all",
    kind: Literal["all", "cinema", "streaming"] = "all",
    page: int = Query(1, ge=1, le=10),
    days: int = Query(120, ge=7, le=365),
    ctx: Ctx = Depends(get_ctx),
):
    """kind : "cinema" (sorties en salles), "streaming" (sorties numériques + séries) ou "all"."""
    types = ["movie", "tv"] if media_type == "all" else [media_type]
    lists = await asyncio.gather(*(ctx.tmdb.upcoming(mt, page, days, kind) for mt in types))
    items = [i for lst in lists for i in lst if i.get("release_date")]
    items.sort(key=lambda i: i["release_date"])
    await enrich(ctx, items)
    return {"results": items, "page": page, "mock": ctx.tmdb.is_mock}


@router.get("/on_the_air")
async def on_the_air(page: int = 1, ctx: Ctx = Depends(get_ctx)):
    items = await ctx.tmdb.on_the_air(page)
    await enrich(ctx, items)
    return {"results": items, "page": page, "mock": ctx.tmdb.is_mock}


@router.get("/genres")
async def genres(ctx: Ctx = Depends(get_ctx)):
    movie, tv = await asyncio.gather(ctx.tmdb.genres("movie"), ctx.tmdb.genres("tv"))
    return {"movie": movie, "tv": tv}


@router.get("/collection/{collection_id}")
async def collection(collection_id: int, ctx: Ctx = Depends(get_ctx)):
    data = await ctx.tmdb.collection(collection_id)
    await enrich(ctx, data["parts"], providers=False)
    return data


@router.get("/tv/{tv_id}/season/{season_number}")
async def season(tv_id: int, season_number: int, ctx: Ctx = Depends(get_ctx)):
    return await ctx.tmdb.season(tv_id, season_number)


@router.get("/{media_type}/{tmdb_id}")
async def detail(media_type: MediaType, tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    """Fiche TMDB seule. La fiche complète agrégée est sur /api/media/{type}/{id}."""
    return await ctx.tmdb.detail(media_type, tmdb_id)


@router.get("/{media_type}/{tmdb_id}/providers")
async def providers(media_type: MediaType, tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    data = await ctx.tmdb.providers(media_type, tmdb_id)
    return {**data, "country": ctx.country, "mock": ctx.tmdb.is_mock}


@router.get("/{media_type}/{tmdb_id}/similar")
async def similar(media_type: MediaType, tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    try:
        items = await ctx.tmdb.recommendations(media_type, tmdb_id)
    except ServiceError:
        items = []
    if not items:
        items = await ctx.tmdb.similar(media_type, tmdb_id)
    await enrich(ctx, items)
    return {"results": items, "mock": ctx.tmdb.is_mock}
