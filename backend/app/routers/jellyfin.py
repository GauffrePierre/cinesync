"""Jellyfin / Emby : connexion du serveur (admin), compte relié de chaque utilisateur, images relayées."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models import User, UserSettings
from app.services.auth import guard_attempts, login_limiter, require_admin
from app.services.cache import cache
from app.services.context import Ctx, get_ctx
from app.services.errors import NotConfigured, ServiceError
from app.services.jellyfin_client import ITEM_ID, JellyfinClient

router = APIRouter(prefix="/jellyfin", tags=["jellyfin"])

class ServerIn(BaseModel):
    url: str = Field(max_length=300)
    public_url: str = Field("", max_length=300)
    api_key: str = Field(max_length=200)


class LinkIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field("", max_length=256)


def _clean_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+", url):
        raise HTTPException(422, "Adresse invalide : elle doit commencer par http:// ou https://")
    return url


@router.post("/server", dependencies=[Depends(require_admin)])
async def connect_server(body: ServerIn, ctx: Ctx = Depends(get_ctx)):
    """Relie le serveur : vérifie l'adresse et la clé API, enregistre nom, identifiant et type (Jellyfin ou Emby)."""
    url = _clean_url(body.url)
    public = _clean_url(body.public_url) if body.public_url.strip() else ""
    probe = JellyfinClient(url, body.api_key)
    info = await probe.public_info()
    probe.kind = info["kind"]
    await probe.users()  # la clé doit être une clé API d'administration
    s = ctx.settings.shared
    s.jellyfin_url, s.jellyfin_public_url, s.jellyfin_api_key = url, public, body.api_key.strip()
    s.jellyfin_server_id, s.jellyfin_server_name, s.jellyfin_kind = info["id"], info["name"], info["kind"]
    ctx.db.commit()
    cache.clear("jellyfin")
    return {"ok": True, "server": info["name"], "kind": info["kind"], "version": info["version"]}


@router.delete("/server", dependencies=[Depends(require_admin)])
def disconnect_server(ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings.shared
    s.jellyfin_url = s.jellyfin_public_url = s.jellyfin_api_key = s.jellyfin_server_id = s.jellyfin_server_name = ""
    ctx.db.commit()
    cache.clear("jellyfin")
    return {"ok": True}


@router.get("/users", dependencies=[Depends(require_admin)])
async def server_users(ctx: Ctx = Depends(get_ctx)):
    """Comptes du serveur et compte SynCiné relié à chacun."""
    if not ctx.jellyfin_admin:
        raise NotConfigured("jellyfin", "Serveur Jellyfin non relié")
    linked = {
        st.jellyfin_user_id: st.id
        for st in ctx.db.execute(select(UserSettings).where(UserSettings.jellyfin_user_id != "")).scalars()
    }
    names = {u.id: u.name for u in ctx.db.query(User).all()}
    return {"results": [
        {**u, "account_id": linked.get(u["id"]), "account_name": names.get(linked.get(u["id"]))}
        for u in await ctx.jellyfin_admin.users() if not u["disabled"]
    ]}


@router.post("/link")
async def link_account(body: LinkIn, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Relie le compte Jellyfin / Emby de l'utilisateur (identifiant + mot de passe, vérifiés par le serveur)."""
    s = ctx.settings
    if not s.jellyfin_url:
        raise NotConfigured("jellyfin", "Serveur Jellyfin non relié par l'administrateur")
    keys = guard_attempts(request, f"jellyfin:{ctx.user.id}")
    client = JellyfinClient(s.jellyfin_url, "", "", s.jellyfin_server_id, s.jellyfin_public_url, s.jellyfin_kind)
    try:
        auth = await client.authenticate(body.username.strip(), body.password)
    except ServiceError as e:
        if e.status == 401:
            login_limiter.fail(*keys)
            raise HTTPException(403, "Identifiant ou mot de passe Jellyfin incorrect") from e
        raise
    other = ctx.db.execute(
        select(UserSettings.id).where(UserSettings.jellyfin_user_id == auth["user_id"], UserSettings.id != ctx.user.id)
    ).first()
    if other:
        raise HTTPException(409, "Ce compte Jellyfin est déjà relié à un autre compte SynCiné")
    own = s.own
    own.jellyfin_user_id, own.jellyfin_username, own.jellyfin_token = auth["user_id"], auth["name"], auth["token"]
    ctx.db.commit()
    login_limiter.reset(*keys)
    cache.clear("jellyfin")
    return {"ok": True, "username": auth["name"]}


@router.delete("/link")
def unlink_account(ctx: Ctx = Depends(get_ctx)):
    own = ctx.settings.own
    own.jellyfin_user_id = own.jellyfin_username = own.jellyfin_token = ""
    ctx.db.commit()
    cache.clear("jellyfin")
    return {"ok": True}


@router.get("/image/{item_id}")
async def image(item_id: str, w: int = Query(342, ge=50, le=1920), kind: str = "Primary", ctx: Ctx = Depends(get_ctx)):
    """Image d'un titre, relayée (l'adresse interne du serveur et la clé ne quittent pas SynCiné)."""
    if not ITEM_ID.match(item_id) or kind not in ("Primary", "Backdrop"):
        raise HTTPException(404, "Image introuvable")
    client = ctx.jellyfin
    if client is None:
        raise NotConfigured("jellyfin")
    content, ctype = await client.image(item_id, w, kind)
    return Response(content=content, media_type=ctype, headers={"Cache-Control": "private, max-age=604800"})


def status_for(ctx: Ctx) -> dict:
    """État Jellyfin pour l'interface (aucune adresse ni clé)."""
    s = ctx.settings
    configured = bool(s.jellyfin_url and (ctx.jellyfin is not None))
    return {
        "configured": configured,
        "server_linked": bool(s.jellyfin_url),
        "server": (s.jellyfin_server_name or None) if configured or ctx.is_admin else None,
        "kind": s.jellyfin_kind or "jellyfin",
        "linked": bool(s.own.jellyfin_user_id),
        "username": s.own.jellyfin_username or None,
    }

