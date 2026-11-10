"""Mode swipe : file de cartes + enregistrement des actions (et synchronisation Trakt)."""

import asyncio
import random
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select

from app.models import SwipeHistory
from app.schemas.swipe import SwipeIn, SwipeOut
from app.services import library_sync
from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich
from app.services.errors import ServiceError
from app.services.suggestions import excluded_keys, suggestions

router = APIRouter(prefix="/swipe", tags=["swipe"])


async def _safe(coro):
    try:
        return await coro
    except ServiceError:
        return []


@router.get("/queue")
async def queue(
    media_type: Literal["all", "movie", "tv"] = "all",
    count: int = Query(20, ge=1, le=50),
    ctx: Ctx = Depends(get_ctx),
):
    types = ["movie", "tv"] if media_type == "all" else [media_type]
    excluded = await excluded_keys(ctx)

    personal = await suggestions(ctx, media_type, limit=count, with_enrich=False)
    pools = await asyncio.gather(
        *(_safe(ctx.tmdb.trending(mt, random.randint(1, 3))) for mt in types),
        *(
            _safe(ctx.tmdb.discover(mt, page=random.randint(1, 15), sort_by="popularity.desc", **{"vote_count.gte": 300}))
            for mt in types
        ),
    )
    discovery = [i for pool in pools for i in pool]
    random.shuffle(discovery)

    # ~60 % personnalisé, le reste en découverte
    out, seen = [], set()
    n_personal = int(count * 0.6)
    for item in personal[:n_personal] + discovery + personal[n_personal:]:
        k = (item["media_type"], item["id"])
        if k in seen or k in excluded:
            continue
        if not ctx.tmdb.is_mock and not item.get("poster"):
            continue
        seen.add(k)
        out.append(item)
        if len(out) >= count:
            break
    random.shuffle(out)
    await enrich(ctx, out)
    return {"results": out, "mock": ctx.tmdb.is_mock}


@router.post("", response_model=SwipeOut)
async def swipe(body: SwipeIn, ctx: Ctx = Depends(get_ctx)):
    row = ctx.db.execute(
        select(SwipeHistory).where(SwipeHistory.tmdb_id == body.tmdb_id, SwipeHistory.media_type == body.media_type)
    ).scalar_one_or_none()
    if row is None:
        row = SwipeHistory(tmdb_id=body.tmdb_id, media_type=body.media_type)
        ctx.db.add(row)
    # Mémoire du swipe : étoiles entières (4,5 -> 4) ; la note exacte (sur 10) part dans la bibliothèque
    row.action, row.rating, row.title = body.action, int(body.rating) if body.rating else None, body.title
    ctx.db.commit()

    if body.action == "skip":
        return SwipeOut(ok=True, trakt_synced=False)

    # Déjà vu -> historique (+ note) ; watchlist -> watchlist ; j'aime -> watchlist + favori
    steps = {"seen": ["watched"] + (["rate"] if body.rating else []), "watchlist": ["watchlist_add"], "like": ["watchlist_add", "like"]}[body.action]
    services: dict[str, str] = {}
    for step in steps:
        res = await library_sync.act(ctx, step, body.media_type, body.tmdb_id, round((body.rating or 0) * 2) or None, body.title)
        for name, v in res["services"].items():
            if services.get(name, "ok") == "ok":
                services[name] = v
    failed = {n: v for n, v in services.items() if v != "ok"}
    if not services:
        return SwipeOut(ok=True, trakt_synced=False, message="Enregistré dans SynCiné — connecte Trakt ou Plex pour synchroniser")
    if failed:
        detail = " ; ".join(f"{n.capitalize()} : {v}" for n, v in failed.items())
        return SwipeOut(ok=True, trakt_synced=False, message=f"Enregistré, mais certains services ont échoué ({detail})")
    return SwipeOut(ok=True, trakt_synced=True)


@router.post("/undo")
async def undo(ctx: Ctx = Depends(get_ctx)):
    """Annule le dernier swipe (localement ; retire aussi de la watchlist Trakt si besoin)."""
    row = ctx.db.execute(select(SwipeHistory).order_by(SwipeHistory.id.desc()).limit(1)).scalar_one_or_none()
    if row is None:
        return {"ok": False, "item": None}
    item = {"tmdb_id": row.tmdb_id, "media_type": row.media_type, "action": row.action}
    if row.action in ("watchlist", "like"):
        await library_sync.act(ctx, "watchlist_remove", row.media_type, row.tmdb_id)
    ctx.db.delete(row)
    ctx.db.commit()
    return {"ok": True, "item": item}


@router.get("/stats")
def stats(ctx: Ctx = Depends(get_ctx)):
    counts = dict(ctx.db.execute(select(SwipeHistory.action, func.count()).group_by(SwipeHistory.action)).all())
    return {"counts": counts, "total": sum(counts.values())}


@router.delete("/history")
def reset(action: Literal["skip", "seen", "watchlist", "like"] | None = None, ctx: Ctx = Depends(get_ctx)):
    q = delete(SwipeHistory)
    if action:
        q = q.where(SwipeHistory.action == action)
    res = ctx.db.execute(q)
    ctx.db.commit()
    return {"deleted": res.rowcount}
