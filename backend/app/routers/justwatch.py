"""JustWatch (non officiel) : nouveautés sur tes plateformes."""

from fastapi import APIRouter, Depends, Query

from app.services.context import Ctx, get_ctx
from app.services.enrich import plex_keys, refs_to_items
from app.services.errors import NotConfigured

router = APIRouter(prefix="/justwatch", tags=["justwatch"])


@router.get("/charts")
async def charts(media_type: str = "movie", ctx: Ctx = Depends(get_ctx)):
    """Top du jour JustWatch dans ton pays (films ou séries)."""
    if not ctx.justwatch:
        raise NotConfigured("justwatch")
    from app.services.enrich import enrich

    refs = await ctx.justwatch.charts("movie" if media_type == "movie" else "tv", 10)
    items = await refs_to_items(ctx, refs)
    await enrich(ctx, items)
    items.sort(key=lambda i: i.get("rank") or 99)
    return {"results": items}


@router.get("/new")
async def new_on_platforms(days: int = Query(7, ge=1, le=14), ctx: Ctx = Depends(get_ctx)):
    if not ctx.justwatch:
        raise NotConfigured("justwatch")
    if not ctx.platforms:
        return {"results": [], "message": "Choisis tes plateformes dans le Profil"}

    raw = await ctx.justwatch.new_titles(ctx.platforms, days)
    # Une entrée par titre (la plus récente), en gardant toutes les plateformes concernées
    merged: dict[tuple[str, int], dict] = {}
    for r in raw:
        k = (r["media_type"], r["tmdb_id"])
        if k not in merged:
            merged[k] = {**r, "platforms": []}
        if r["provider"]["id"] not in {p["id"] for p in merged[k]["platforms"]}:
            merged[k]["platforms"].append({**r["provider"], "url": r["url"]})
    refs = sorted(merged.values(), key=lambda r: r["date"], reverse=True)[:80]

    items = await refs_to_items(ctx, refs)
    index = await plex_keys(ctx)
    for i in items:
        i["in_plex"] = (i["media_type"], i["id"]) in index
        i["providers"] = i.pop("platforms", [])
        i.pop("provider", None)
    return {"results": items}
