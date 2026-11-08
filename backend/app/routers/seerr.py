"""Seerr : statut d'un titre. Les demandes passent par /requests (droits par compte, file de l'admin)."""

from typing import Literal

from fastapi import APIRouter, Depends

from app.services.context import Ctx, get_ctx

router = APIRouter(prefix="/seerr", tags=["seerr"])


@router.get("/status/{media_type}/{tmdb_id}")
async def status(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    if not ctx.seerr:
        return {"configured": False}
    status = await ctx.seerr.media_status(media_type, tmdb_id)
    if not ctx.is_admin:
        status.pop("url", None)  # adresse de Seerr : admin seulement
    return {"configured": True, **status}

