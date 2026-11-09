"""Jellyfin / Emby : connexion du serveur (admin), compte relié de chaque utilisateur, images relayées."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from app.models import Notification, User, UserSettings
from app.services import messages
from app.services.auth import confirm_identity, guard_attempts, jellyfin_limiter, login_limiter, require_admin
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
    username: str = Field(min_length=1, max_length=100)
    password: str = Field("", max_length=256)
    current_password: str = Field("", max_length=256)  # mot de passe SynCiné (sans mot de passe : connexion récente)


def _forget_links(ctx: Ctx) -> None:
    """Serveur délié ou remplacé : plus aucun compte relié ni connexion par Jellyfin (les jetons n'iraient pas à un
    autre serveur)."""
    ctx.db.execute(update(UserSettings).values(jellyfin_user_id="", jellyfin_username="", jellyfin_token=""))
    ctx.db.execute(update(User).values(jellyfin_login=False))


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
    if s.jellyfin_server_id and s.jellyfin_server_id != info["id"]:
        _forget_links(ctx)  # un autre serveur : les comptes reliés à l'ancien ne valent plus rien
    s.jellyfin_url, s.jellyfin_public_url, s.jellyfin_api_key = url, public, body.api_key.strip()
    s.jellyfin_server_id, s.jellyfin_server_name, s.jellyfin_kind = info["id"], info["name"], info["kind"]
    ctx.db.commit()
    cache.clear("jellyfin")
    return {"ok": True, "server": info["name"], "kind": info["kind"], "version": info["version"]}


@router.delete("/server", dependencies=[Depends(require_admin)])
def disconnect_server(ctx: Ctx = Depends(get_ctx)):
    s = ctx.settings.shared
    s.jellyfin_url = s.jellyfin_public_url = s.jellyfin_api_key = s.jellyfin_server_id = s.jellyfin_server_name = ""
    _forget_links(ctx)
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
    """Relie le compte Jellyfin / Emby de l'utilisateur (identifiant + mot de passe, vérifiés par le serveur), pour sa
    bibliothèque et ses vus. Ne permet pas de se connecter à SynCiné avec ce compte : c'est l'administrateur qui
    l'autorise. Mot de passe SynCiné exigé (ou connexion récente), et l'utilisateur est prévenu."""
    s = ctx.settings
    if not s.jellyfin_url:
        raise NotConfigured("jellyfin", "Serveur Jellyfin non relié par l'administrateur")
    confirm_identity(ctx.db, request, ctx.user, body.current_password)
    if await _client(s).quick_connect_enabled():  # le mot de passe Jellyfin n'est alors jamais saisi ici
        raise HTTPException(409, "Ce serveur Jellyfin utilise Quick Connect : relie ton compte avec un code Quick Connect")
    username = body.username.strip()
    keys = guard_attempts(request, f"jflink:{ctx.user.id}")
    target = f"jf:{username.lower()}"
    if jellyfin_limiter.blocked(target):
        raise HTTPException(429, "Trop d'essais pour ce compte Jellyfin : réessaie demain")
    client = JellyfinClient(s.jellyfin_url, "", "", s.jellyfin_server_id, s.jellyfin_public_url, s.jellyfin_kind, device=username)
    try:
        auth = await client.authenticate(username, body.password)
    except ServiceError as e:
        if e.status == 401:
            login_limiter.fail(*keys)
            jellyfin_limiter.fail(target)
            raise HTTPException(403, "Identifiant ou mot de passe Jellyfin incorrect") from e
        raise
    await _store_link(ctx, auth, client.label)
    login_limiter.reset(*keys)
    jellyfin_limiter.reset(target)
    return {"ok": True, "username": auth["name"]}


def _client(s, device: str = "", token: str = "", user_id: str = "") -> JellyfinClient:
    return JellyfinClient(s.jellyfin_url, token, user_id, s.jellyfin_server_id, s.jellyfin_public_url, s.jellyfin_kind, device=device)


async def _store_link(ctx: Ctx, auth: dict, label: str) -> None:
    """Enregistre le compte relié (sans autoriser la connexion par Jellyfin) ; l'ancien jeton est révoqué et
    l'utilisateur prévenu."""
    other = ctx.db.execute(
        select(UserSettings.id).where(UserSettings.jellyfin_user_id == auth["user_id"], UserSettings.id != ctx.user.id)
    ).first()
    if other:
        await _revoke(ctx.settings, auth["token"], auth["user_id"])
        raise HTTPException(409, "Ce compte Jellyfin est déjà relié à un autre compte SynCiné")
    own = ctx.settings.own
    if own.jellyfin_token and own.jellyfin_token != auth["token"]:
        await _revoke(ctx.settings, own.jellyfin_token, own.jellyfin_user_id)
    if own.jellyfin_user_id != auth["user_id"]:
        ctx.user.jellyfin_login = False  # autre compte : la connexion par Jellyfin doit être de nouveau autorisée
    own.jellyfin_user_id, own.jellyfin_username, own.jellyfin_token = auth["user_id"], auth["name"], auth["token"]
    ctx.db.add(Notification(user_id=ctx.user.id, kind="service", service="security", **messages.fields(
        "Le compte {server} « {name} » a été relié à ton compte SynCiné. Si ce n'était pas toi, change ton mot de passe.",
        server=label, name=auth["name"])))
    ctx.db.commit()
    cache.clear("jellyfin")


async def _revoke(s, token: str, user_id: str) -> None:
    try:
        await _client(s, token=token, user_id=user_id).logout()
    except ServiceError:
        pass  # serveur injoignable : sans effet sur SynCiné


class QuickLinkIn(BaseModel):
    current_password: str = Field("", max_length=256)


@router.post("/link/quickconnect")
async def link_quick_connect_start(body: QuickLinkIn, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Relier son compte par Quick Connect, étape 1 (mot de passe SynCiné ou connexion récente exigés)."""
    from app.services import quick_connect
    from app.services.auth import client_ip

    s = ctx.settings
    if not s.jellyfin_url:
        raise NotConfigured("jellyfin", "Serveur Jellyfin non relié par l'administrateur")
    confirm_identity(ctx.db, request, ctx.user, body.current_password)
    ip = client_ip(request)
    if not quick_connect.can_start(ip):
        raise HTTPException(429, "Trop de demandes en attente, réessaie dans quelques minutes")
    device = quick_connect.new_device()
    started = await _client(s, device).quick_connect_start()
    key = quick_connect.add(quick_connect.Pending(started["secret"], started["code"], device, "link", ip, ctx.user.id))
    return {"id": key, "code": started["code"], "expires_in": quick_connect.TTL}


@router.post("/link/quickconnect/{key}")
async def link_quick_connect_check(key: str, ctx: Ctx = Depends(get_ctx)):
    """Étape 2 (interrogée toutes les 2 s) : en attente, ou compte relié une fois le code validé dans Jellyfin."""
    from app.services import quick_connect

    pending = quick_connect.get(key, "link", ctx.user.id)
    if pending is None:
        raise HTTPException(410, "Code expiré : recommence")
    client = _client(ctx.settings, pending.device)
    if not await client.quick_connect_approved(pending.secret):
        return {"status": "pending"}
    quick_connect.drop(key)
    auth = await client.quick_connect_auth(pending.secret)
    await _store_link(ctx, auth, client.label)
    return {"ok": True, "status": "linked", "username": auth["name"]}


@router.delete("/link")
async def unlink_account(ctx: Ctx = Depends(get_ctx)):
    """Délie le compte : jeton révoqué sur le serveur (si possible) et connexion par Jellyfin retirée."""
    own = ctx.settings.own
    if own.jellyfin_token and ctx.settings.jellyfin_url:
        await _revoke(ctx.settings, own.jellyfin_token, own.jellyfin_user_id)  # le lien est retiré même si ça échoue
    own.jellyfin_user_id = own.jellyfin_username = own.jellyfin_token = ""
    ctx.user.jellyfin_login = False
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
    # Servie depuis l'origine de SynCiné : jamais interprétée comme une page (bac à sable, type vérifié)
    return Response(content=content, media_type=ctype, headers={
        "Cache-Control": "private, max-age=604800", "Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"})


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

