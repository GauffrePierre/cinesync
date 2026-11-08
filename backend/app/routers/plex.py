"""Endpoints Plex : bibliothèque, recherche, statut d'un titre, images relayées."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import plex_auth
from app.services.cache import cache
from app.services.auth import require_admin
from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich
from app.services.errors import NotConfigured, ServiceError

router = APIRouter(prefix="/plex", tags=["plex"])

SORTS = {
    "added": (lambda i: i.get("added_at") or "", True),
    "title": (lambda i: (i.get("title") or "").lower(), False),
    "rating": (lambda i: i.get("vote_average") or 0, True),
    "year": (lambda i: i.get("year") or 0, True),
}


@router.get("/sections")
async def sections(ctx: Ctx = Depends(get_ctx)):
    p = ctx.plex_or_mock
    return {"results": await p.sections(), "mock": p.is_mock}


@router.get("/library")
async def library(
    media_type: Literal["all", "movie", "tv"] = "all",
    sort: Literal["added", "title", "rating", "year"] = "added",
    section_id: str | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    with_providers: bool = True,
    ctx: Ctx = Depends(get_ctx),
):
    p = ctx.plex_or_mock
    items = await p.library()
    if media_type != "all":
        items = [i for i in items if i["media_type"] == media_type]
    if section_id:
        items = [i for i in items if i.get("section_id") == section_id]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i.get("title") or "").lower()]
    key, reverse = SORTS[sort]
    items = sorted(items, key=key, reverse=reverse)
    total = len(items)
    page_items = [dict(i) for i in items[(page - 1) * page_size : page * page_size]]
    if with_providers:
        await enrich(ctx, [i for i in page_items if i.get("id")], plex=False)
    return {"results": page_items, "total": total, "page": page, "page_size": page_size, "mock": p.is_mock}


@router.get("/sections/{section_id}/items")
async def section_items(section_id: str, ctx: Ctx = Depends(get_ctx)):
    p = ctx.plex_or_mock
    items = [i for i in await p.library() if i.get("section_id") == section_id]
    return {"results": items, "mock": p.is_mock}


@router.get("/search")
async def search(q: str = Query(..., min_length=1), ctx: Ctx = Depends(get_ctx)):
    p = ctx.plex_or_mock
    return {"results": await p.search(q), "mock": p.is_mock}


@router.get("/status/{media_type}/{tmdb_id}")
async def status(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    if not ctx.plex:
        return {"configured": False, "available": False}
    hit = (await ctx.plex.index()).get((media_type, tmdb_id))
    return {"configured": True, "available": hit is not None, "url": hit.get("plex_url") if hit else None}


@router.get("/image")
async def image(path: str, width: int = Query(342, ge=50, le=1920), ctx: Ctx = Depends(get_ctx)):
    if not ctx.plex:
        raise NotConfigured("plex")
    content, ctype = await ctx.plex.image(path, width)
    return Response(content=content, media_type=ctype, headers={"Cache-Control": "private, max-age=604800"})


# --- Connexion via le compte plex.tv ----------------------------------------------


class ServerChoice(BaseModel):
    machine_id: str


def _client_id(ctx: Ctx) -> str:
    if not ctx.settings.plex_client_id:
        ctx.settings.plex_client_id = str(uuid.uuid4())
        ctx.db.commit()
    return ctx.settings.plex_client_id


def _apply_server(ctx: Ctx, server: dict) -> dict:
    """Enregistre le serveur choisi : URL de la meilleure connexion + jeton du serveur."""
    conn = server.get("connection")
    if not conn:
        raise ServiceError("plex", f"Le serveur « {server['name']} » est injoignable depuis SynCiné", 502)
    s = ctx.settings.shared  # le serveur est celui de toute la famille
    s.plex_url = conn["uri"]
    s.plex_token = server["_raw"].get("accessToken") or s.plex_account_token
    s.plex_server_name = server["name"] or ""
    s.plex_machine_id = server["machine_id"] or ""
    ctx.db.commit()
    cache.clear("plex")
    return {"name": server["name"], "machine_id": server["machine_id"], "connection": conn}


# Connexion du serveur (compte Plex de l'admin) : réservé à l'administrateur.
# Les membres se connectent avec Plex depuis l'écran de connexion (routers/auth.py).


# Codes créés ici, par compte admin : seul un code que cet admin a lui-même demandé peut relier un compte Plex
# (sinon un lien piégé pourrait faire relier le compte Plex d'un tiers au serveur de la famille)
_server_pins: dict[int, tuple[int, float]] = {}  # pin -> (id du compte, expiration)


def _main_admin_only(ctx: Ctx) -> None:
    """Le compte plex.tv qui relie le serveur est aussi celui du compte principal (watchlist, notes) :
    un autre admin le remplacerait et mélangerait ses données avec celles du compte principal."""
    from app.services.context import SHARED_ID

    if ctx.user.id != SHARED_ID:
        raise HTTPException(403, "Seul le compte administrateur principal peut relier le serveur Plex")


@router.post("/auth/pin", dependencies=[Depends(require_admin)])
async def auth_pin(request: Request, mode: Literal["link", "window"] = "link", ctx: Ctx = Depends(get_ctx)):
    """Étape 1 : crée un code. "link" : à saisir sur plex.tv/link. "window" : fenêtre app.plex.tv."""
    import time

    from app.config import config

    _main_admin_only(ctx)
    base = (config.public_url or str(request.base_url)).rstrip("/")  # retour : toujours la page de SynCiné
    pin = await plex_auth.create_pin(_client_id(ctx), mode, f"{base}/plex-done.html" if mode == "window" else None)
    now = time.monotonic()
    for k in [k for k, (_, exp) in _server_pins.items() if exp < now]:
        _server_pins.pop(k, None)
    _server_pins[pin["id"]] = (ctx.user.id, now + pin["expires_in"])
    return pin


@router.post("/auth/pin/{pin_id}", dependencies=[Depends(require_admin)])
async def auth_check(pin_id: int, ctx: Ctx = Depends(get_ctx)):
    """Étape 2 (interrogée en boucle) : une fois connecté, renvoie la liste de tes serveurs.
    POST : la vérification d'origine (anti-CSRF) s'applique ; le code doit venir de ce même admin."""
    import time

    _main_admin_only(ctx)
    owner = _server_pins.get(pin_id)
    if owner is None or owner[0] != ctx.user.id or owner[1] < time.monotonic():
        raise ServiceError("plex", "Code de connexion Plex expiré — recommence", 410)
    cid = _client_id(ctx)
    token = await plex_auth.check_pin(cid, pin_id)
    if not token:
        return {"authorized": False}
    _server_pins.pop(pin_id, None)
    ctx.settings.shared.plex_account_token = token
    ctx.db.commit()
    servers = await plex_auth.list_servers(cid, token)
    reachable = [s for s in servers if s["connection"]]
    selected = _apply_server(ctx, reachable[0]) if len(reachable) == 1 else None
    return {"authorized": True, "servers": plex_auth.public(servers), "selected": selected}


@router.get("/servers", dependencies=[Depends(require_admin)])
async def servers(ctx: Ctx = Depends(get_ctx)):
    if not ctx.settings.shared.plex_account_token:
        raise NotConfigured("plex", "Connecte-toi d'abord avec ton compte Plex")
    found = await plex_auth.list_servers(_client_id(ctx), ctx.settings.shared.plex_account_token)
    return {"results": plex_auth.public(found), "current": ctx.settings.plex_machine_id or None}


@router.post("/servers/select", dependencies=[Depends(require_admin)])
async def select_server(body: ServerChoice, ctx: Ctx = Depends(get_ctx)):
    if not ctx.settings.shared.plex_account_token:
        raise NotConfigured("plex", "Connecte-toi d'abord avec ton compte Plex")
    found = await plex_auth.list_servers(_client_id(ctx), ctx.settings.shared.plex_account_token)
    server = next((s for s in found if s["machine_id"] == body.machine_id), None)
    if server is None:
        raise ServiceError("plex", "Serveur introuvable sur ce compte Plex", 404)
    return _apply_server(ctx, server)


@router.post("/auth/logout", dependencies=[Depends(require_admin)])
def logout(ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings.shared
    s.plex_account_token = s.plex_url = s.plex_token = s.plex_server_name = s.plex_machine_id = ""
    ctx.db.commit()
    cache.clear("plex")
    return {"ok": True}


@router.get("/watch-link/{media_type}/{tmdb_id}")
async def watch_link(media_type: Literal["movie", "tv"], tmdb_id: int, season: int | None = None, episode: int | None = None, ctx: Ctx = Depends(get_ctx)):
    """Lien watch.plex.tv d'un titre (ouvert par l'app Plex sur iPhone / iPad), ou null."""
    if not ctx.plex_account:
        return {"url": None}
    try:
        return {"url": await ctx.plex_account.watch_url(media_type, tmdb_id, season, episode)}
    except ServiceError:
        return {"url": None}
