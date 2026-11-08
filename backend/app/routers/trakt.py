"""Endpoints Trakt : connexion (code d'appareil / PKCE) et lecture.

Les écritures (watchlist, vu, notes) passent par /api/library, qui les envoie à tous les services."""

import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.services.context import Ctx, get_ctx, public_base_url
from app.services.enrich import enrich, refs_to_items
from app.services.errors import NotConfigured, ServiceError

router = APIRouter(prefix="/trakt", tags=["trakt"])

# Code d'appareil en cours, par compte CinéSync
_device: dict[int, str] = {}


def _redirect_uri(request: Request) -> str:
    return f"{public_base_url(request)}/api/trakt/oauth/callback"


# --- OAuth -------------------------------------------------------------------


@router.get("/oauth/info")
def oauth_info(request: Request, ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings
    redirect = _redirect_uri(request)
    return {
        "redirect_uri": redirect,
        "redirect_https": redirect.startswith("https://"),
        "configured": bool(s.trakt_client_id),
        "connected": bool(s.trakt_access_token),
        "username": s.trakt_username or None,
    }


def _require_app(ctx: Ctx):
    if not ctx.settings.trakt_client_id:
        raise NotConfigured("trakt", "Renseigne d'abord le client ID de ton application Trakt")
    return ctx.trakt_app


# Code d'appareil (recommandé en auto-hébergé : aucune URL de retour à configurer)


@router.post("/device/start")
async def device_start(ctx: Ctx = Depends(get_ctx)):
    data = await _require_app(ctx).device_code()
    _device[ctx.user.id] = data["device_code"]
    return {k: data[k] for k in ("user_code", "verification_url", "expires_in", "interval")}


@router.post("/device/poll")
async def device_poll(ctx: Ctx = Depends(get_ctx)):
    code = _device.get(ctx.user.id)
    if not code:
        return {"status": "expired"}
    status = await _require_app(ctx).device_poll(code)
    if status not in ("pending", "slow_down"):
        _device.pop(ctx.user.id, None)
    return {"status": status, "username": ctx.settings.trakt_username or None}


# PKCE (redirection ; Trakt exige une URL de retour HTTPS)


@router.get("/oauth/start")
def oauth_start(request: Request, ctx: Ctx = Depends(get_ctx)):
    client = _require_app(ctx)
    verifier, challenge = client.new_pkce()
    state = secrets.token_urlsafe(24)
    ctx.settings.trakt_oauth_state = state
    ctx.settings.trakt_code_verifier = verifier
    ctx.db.commit()
    return {"url": client.authorize_url(_redirect_uri(request), state, challenge)}


@router.get("/oauth/callback")
async def oauth_callback(request: Request, code: str = "", state: str = "", error: str = "", ctx: Ctx = Depends(get_ctx)):
    base = public_base_url(request)
    if error or not code:
        return RedirectResponse(f"{base}/profile?trakt=error&reason={error or 'no_code'}")
    if not state or state != ctx.settings.trakt_oauth_state or not ctx.settings.trakt_code_verifier:
        return RedirectResponse(f"{base}/profile?trakt=error&reason=state")
    try:
        await ctx.trakt_app.exchange_code(code, _redirect_uri(request), ctx.settings.trakt_code_verifier)
    except ServiceError:
        return RedirectResponse(f"{base}/profile?trakt=error&reason=token")
    return RedirectResponse(f"{base}/profile?trakt=connected")


@router.post("/disconnect")
def disconnect(ctx: Ctx = Depends(get_ctx)):
    if ctx.trakt_app:
        ctx.trakt_app.disconnect()
    return {"ok": True}


# --- Lecture -----------------------------------------------------------------


def _filter(refs: list[dict], media_type: str) -> list[dict]:
    return refs if media_type == "all" else [r for r in refs if r["media_type"] == media_type]


@router.get("/watchlist")
async def watchlist(media_type: Literal["all", "movie", "tv"] = "all", ctx: Ctx = Depends(get_ctx)):
    t = ctx.trakt_or_mock
    refs = _filter(await t.watchlist(), media_type)
    items = await refs_to_items(ctx, refs)
    await enrich(ctx, items)
    return {"results": items, "mock": t.is_mock}


@router.get("/history")
async def history(limit: int = Query(50, ge=1, le=200), ctx: Ctx = Depends(get_ctx)):
    t = ctx.trakt_or_mock
    items = await refs_to_items(ctx, await t.history(limit))
    return {"results": items, "mock": t.is_mock}


@router.get("/ratings")
async def ratings(ctx: Ctx = Depends(get_ctx)):
    t = ctx.trakt_or_mock
    items = await refs_to_items(ctx, await t.ratings())
    return {"results": items, "mock": t.is_mock}


@router.get("/recommendations")
async def recommendations(media_type: Literal["movie", "tv"] = "movie", ctx: Ctx = Depends(get_ctx)):
    t = ctx.trakt_or_mock
    items = await refs_to_items(ctx, await t.recommendations(media_type, 30))
    await enrich(ctx, items)
    return {"results": items, "mock": t.is_mock}
