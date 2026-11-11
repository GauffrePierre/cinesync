"""État personnel fusionné (tous services) : watchlist, vu, notes, j'aime, synchronisation."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models import MediaState
from app.services import library_sync
from app.services.context import Ctx, get_ctx
from app.services.enrich import plex_keys, stream_providers
from app.services.errors import ServiceError
from app.services.sorting import Sort, fill_info, sort_items
from app.services.clock import utcnow

router = APIRouter(prefix="/library", tags=["library"])


class Ref(BaseModel):
    tmdb_id: int = Field(gt=0)
    media_type: Literal["movie", "tv"]
    title: str = Field("", max_length=300)


class RatingIn(Ref):
    rating: float = Field(ge=0.5, le=5, multiple_of=0.5)  # étoiles, par demi-étoile (4,5 = 9/10)


def _k(mt: str, tid: int) -> str:
    return f"{mt}:{tid}"


@router.get("/keys")
def keys(ctx: Ctx = Depends(get_ctx)):
    """Vue compacte de tout l'état personnel (pour les boutons et badges des cartes)."""
    out = {"watchlist": [], "watched": [], "liked": [], "disliked": [], "ratings": {}}
    for r in ctx.db.execute(select(MediaState)).scalars():
        k = _k(r.media_type, r.tmdb_id)
        if r.in_watchlist:
            out["watchlist"].append(k)
        if r.watched:
            out["watched"].append(k)
        if r.liked:
            out["liked"].append(k)
        if r.disliked:
            out["disliked"].append(k)
        if r.rating:
            out["ratings"][k] = r.rating
    return out


@router.get("/seen")
async def seen(ctx: Ctx = Depends(get_ctx)):
    """Titres à ne plus proposer (réglage « déjà vus ») : films vus, séries vues sans nouvel épisode depuis."""
    from app.services.suggestions import seen_keys

    return {"keys": sorted(_k(mt, tid) for mt, tid in await seen_keys(ctx))}


@router.get("/state/{media_type}/{tmdb_id}")
def state(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    return library_sync.state_of(ctx.db, media_type, tmdb_id)


@router.get("/watchlist")
async def watchlist(
    media_type: Literal["all", "movie", "tv"] = "all",
    availability: Literal["all", "mine", "none"] = "all",
    seen: Literal["all", "seen", "unseen"] = "all",
    sort: Sort = "added",
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
    ctx: Ctx = Depends(get_ctx),
):
    rows = [r for r in ctx.db.execute(select(MediaState)).scalars() if r.in_watchlist]
    if seen != "all":  # filtre Vus / Pas vus (une série commencée compte comme vue)
        rows = [r for r in rows if r.watched == (seen == "seen")]
    if media_type != "all":
        rows = [r for r in rows if r.media_type == media_type]

    # Disponibilités manquantes : on les récupère (et on les mémorise) avant de filtrer
    unknown = [r for r in rows if r.providers_checked_at is None]
    if unknown and not ctx.tmdb.is_mock:
        sem = asyncio.Semaphore(10)

        async def fill(r: MediaState):
            async with sem:
                try:
                    r.providers = json.dumps(stream_providers(await ctx.tmdb.providers(r.media_type, r.tmdb_id)))
                    r.providers_checked_at = utcnow()
                except ServiceError:
                    pass

        await asyncio.gather(*(fill(r) for r in unknown[:150]))  # par lots, pour garder la page réactive
        ctx.db.commit()

    if sort in ("release", "rating", "critics", "audience", "year"):
        await fill_info(ctx, rows, scores=False)  # sortie et note TMDB manquantes (notes critique / public : tâche périodique)

    index = await plex_keys(ctx)
    platforms = set(ctx.platforms)
    items = []
    for r in rows:
        it = r.to_item()
        it["added"], it["personal_rating"] = r.listed_at, r.rating
        hit = index.get((r.media_type, r.tmdb_id))
        it["in_plex"] = hit is not None
        it["plex_url"] = hit.get("plex_url") if hit else None
        mine = it["in_plex"] or any(p["id"] in platforms for p in it["providers"])
        if availability == "mine" and not mine:
            continue
        if availability == "none" and (it["in_plex"] or it["providers"]):
            continue
        items.append(it)

    items = sort_items(items, sort)
    pending_scores = sum(1 for r in rows if r.info_checked_at is None) if sort in ("critics", "audience") else 0

    total = len(items)
    return {
        "results": items[(page - 1) * page_size : page * page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pending_availability": max(0, len(unknown) - 150),
        "pending_scores": pending_scores,  # notes critique / public encore en cours de récupération
        "last_pull": library_sync.last_pull(ctx) or None,
    }


async def _act(ctx: Ctx, action: str, ref: Ref, rating10: int | None = None):
    return await library_sync.act(ctx, action, ref.media_type, ref.tmdb_id, rating10, ref.title)


@router.post("/watchlist")
async def add_watchlist(body: Ref, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "watchlist_add", body)


@router.delete("/watchlist/{media_type}/{tmdb_id}")
async def remove_watchlist(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "watchlist_remove", Ref(media_type=media_type, tmdb_id=tmdb_id))


@router.post("/watched")
async def mark_watched(body: Ref, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "watched", body)


@router.post("/rating")
async def rate(body: RatingIn, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "rate", body, round(body.rating * 2))


@router.post("/like")
async def like(body: Ref, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "like", body)


@router.post("/dislike")
async def dislike(body: Ref, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "dislike", body)


@router.delete("/dislike/{media_type}/{tmdb_id}")
async def undislike(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "undislike", Ref(media_type=media_type, tmdb_id=tmdb_id))


@router.get("/disliked")
def disliked(ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(MediaState).where(MediaState.disliked.is_(True)).order_by(MediaState.updated_at.desc())).scalars()
    return {"results": [r.to_item() for r in rows]}


@router.delete("/watched/{media_type}/{tmdb_id}")
async def unwatch(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "unwatched", Ref(media_type=media_type, tmdb_id=tmdb_id))


@router.delete("/like/{media_type}/{tmdb_id}")
async def unlike(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    return await _act(ctx, "unlike", Ref(media_type=media_type, tmdb_id=tmdb_id))


@router.get("/sync")
def sync_status(ctx: Ctx = Depends(get_ctx)):
    sources = {
        "trakt": ctx.trakt is not None,
        "plex": ctx.plex_account is not None or ctx.plex_own is not None,
        "letterboxd": ctx.letterboxd is not None,
    }
    return {"last_pull": library_sync.last_pull(ctx) or None, "sources": sources, "auto_sync": ctx.settings.auto_sync}


@router.post("/sync")
async def sync_now(max_age: int = Query(0, ge=0, le=3600), ctx: Ctx = Depends(get_ctx)):
    """Lance une synchronisation. max_age (s) : ne rien faire si la dernière date de moins de max_age
    (utilisé à l'ouverture de l'appli, pour ne pas resynchroniser à chaque rechargement)."""
    last = library_sync.last_pull(ctx)
    if max_age and last.get("at"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last["at"])).total_seconds()
        if age < max_age:
            return {**last, "skipped": True}
    from app.services.history import import_all

    result = await library_sync.pull(ctx)
    result["history"] = await import_all(ctx)
    return result


@router.get("/sync/preview")
async def sync_preview(ctx: Ctx = Depends(get_ctx)):
    """Simulation : ce que la synchronisation bidirectionnelle ajouterait / retirerait sur chaque service."""
    return await library_sync.preview(ctx)
