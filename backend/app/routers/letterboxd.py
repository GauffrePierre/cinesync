"""Letterboxd : derniers films vus (flux RSS public)."""

from fastapi import APIRouter, Depends

from app.services.context import Ctx, get_ctx
from app.services.errors import NotConfigured

router = APIRouter(prefix="/letterboxd", tags=["letterboxd"])


@router.get("/diary")
async def diary(ctx: Ctx = Depends(get_ctx)):
    if not ctx.letterboxd:
        raise NotConfigured("letterboxd")
    return {"results": await ctx.letterboxd.diary(), "username": ctx.settings.letterboxd_username}
