"""Connexion à SynCiné avec un compte Plex ou Jellyfin / Emby (comptes autorisés par l'administrateur) : code
plex.tv lié au navigateur, mot de passe ou Quick Connect Jellyfin. Sessions, 2FA et mots de passe : routers/auth.py."""

import hmac
import secrets
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import app.database as database
from app.config import config
from app.database import get_db
from app.models import User
from app.routers.auth import _first_admin, _me, _two_factor_ticket, server_only
from app.services import auth, plex_auth
from app.services.auth import guard_attempts, login_limiter
from app.services.context import SHARED_ID, settings_for
from app.services.errors import ServiceError
from app.services.history import assign_plex_events

router = APIRouter(prefix="/auth", tags=["auth"])


PIN_COOKIE = "cinesync_plex_pin"
_pending_pins: dict[int, tuple[str, float]] = {}  # pin plex.tv -> (jeton du navigateur, expiration)
MAX_PENDING_PINS = 500


class JellyfinLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)  # jamais de mot de passe vide (comptes sans mot de passe)


@router.post("/jellyfin", dependencies=server_only)
async def login_jellyfin(body: JellyfinLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Connexion avec un compte Jellyfin / Emby que l'administrateur a autorisé (mot de passe vérifié par le serveur).

    Le serveur n'est interrogé que pour un compte autorisé : SynCiné ne sert pas à tester des mots de passe sur
    les autres comptes du serveur, et chaque compte visé n'a que deux essais par jour (sous le seuil de blocage
    du serveur). Toutes les erreurs donnent la même réponse."""
    from app.models import UserSettings
    from app.services.errors import ServiceError
    from app.services.jellyfin_client import JellyfinClient

    shared = settings_for(db, SHARED_ID).shared
    if not shared.jellyfin_url:
        raise HTTPException(404, "La connexion avec Jellyfin n'est pas activée sur ce SynCiné")
    if await _jellyfin_client(shared).quick_connect_enabled():  # le mot de passe Jellyfin n'est alors jamais saisi ici
        raise HTTPException(409, "Ce serveur Jellyfin utilise Quick Connect : connecte-toi avec un code Quick Connect")
    username = body.username.strip()
    own = (
        db.query(UserSettings).join(User, User.id == UserSettings.id)
        .filter(func.lower(UserSettings.jellyfin_username) == username.lower(), UserSettings.jellyfin_user_id != "",
                User.jellyfin_login.is_(True), User.active.is_(True))
        .first()
    )
    user = db.get(User, own.id) if own else None
    known = user is not None and auth.known_device(request) == user.id
    keys = guard_attempts(request, f"jflogin:{username.lower()}", trusted=known)
    limiter, target = auth.jellyfin_guard(username, known)
    refused = HTTPException(401, "Identifiant ou mot de passe incorrect")
    if user is None:
        login_limiter.fail(*keys)
        raise refused
    client = JellyfinClient(shared.jellyfin_url, "", "", shared.jellyfin_server_id, shared.jellyfin_public_url, shared.jellyfin_kind,
                            device=username)
    try:
        info = await client.authenticate(username, body.password)
    except ServiceError as e:
        if e.status == 401:
            login_limiter.fail(*keys)
            limiter.fail(target)
            raise refused from e
        raise
    if info["user_id"] != own.jellyfin_user_id:  # autre compte du serveur sous ce nom (renommage) : refusé
        login_limiter.fail(*keys)
        raise refused
    login_limiter.reset(*keys)
    auth.jellyfin_release(username)
    return await _jellyfin_session(db, request, response, user, own, info, shared)


def _jellyfin_client(shared, device: str = ""):
    from app.services.jellyfin_client import JellyfinClient

    return JellyfinClient(shared.jellyfin_url, "", "", shared.jellyfin_server_id, shared.jellyfin_public_url, shared.jellyfin_kind, device=device)


async def _jellyfin_session(db: Session, request: Request, response: Response, user: User, own, info: dict, shared):
    """Connexion réussie avec Jellyfin : nouveau jeton du compte (l'ancien est révoqué), puis session ou 2FA."""
    from app.services.errors import ServiceError
    from app.services.jellyfin_client import JellyfinClient

    if own.jellyfin_token and own.jellyfin_token != info["token"]:
        try:
            await JellyfinClient(shared.jellyfin_url, own.jellyfin_token, own.jellyfin_user_id, kind=shared.jellyfin_kind).logout()
        except ServiceError:
            pass
    own.jellyfin_token, own.jellyfin_username = info["token"], info["name"]  # jeton du compte : sa bibliothèque, ses vus
    db.commit()
    if user.totp_secret:
        return _two_factor_ticket(user)
    auth.open_session(db, user, request, response)
    return _me(db, user)


@router.get("/jellyfin/quickconnect", dependencies=server_only)
async def jellyfin_quick_connect_status(db: Session = Depends(get_db)):
    """Quick Connect disponible sur le serveur Jellyfin relié (sinon : identifiant et mot de passe)."""
    shared = settings_for(db, SHARED_ID).shared
    return {"enabled": bool(shared.jellyfin_url) and await _jellyfin_client(shared).quick_connect_enabled()}


@router.post("/jellyfin/quickconnect", dependencies=server_only)
async def jellyfin_quick_connect_start(request: Request, db: Session = Depends(get_db)):
    """Connexion par Quick Connect, étape 1 : un code à valider dans Jellyfin (profil → Quick Connect)."""
    from app.services import quick_connect

    shared = settings_for(db, SHARED_ID).shared
    if not shared.jellyfin_url or not db.query(User.id).filter(User.jellyfin_login.is_(True), User.active.is_(True)).first():
        raise HTTPException(404, "La connexion avec Jellyfin n'est pas activée sur ce SynCiné")
    ip = auth.client_ip(request)
    if not quick_connect.can_start(ip):
        raise HTTPException(429, "Trop de demandes en attente, réessaie dans quelques minutes")
    device = quick_connect.new_device()
    started = await _jellyfin_client(shared, device).quick_connect_start()
    key = quick_connect.add(quick_connect.Pending(started["secret"], started["code"], device, "login", ip))
    return {"id": key, "code": started["code"], "expires_in": quick_connect.TTL}


@router.post("/jellyfin/quickconnect/{key}", dependencies=server_only)
async def jellyfin_quick_connect_check(key: str, request: Request, response: Response, db: Session = Depends(get_db)):
    """Étape 2 (interrogée toutes les 2 s) : en attente, ou connexion du compte SynCiné autorisé pour ce compte Jellyfin."""
    from app.models import UserSettings
    from app.services import quick_connect
    from app.services.errors import ServiceError
    from app.services.jellyfin_client import JellyfinClient

    pending = quick_connect.get(key, "login")
    if pending is None:
        raise HTTPException(410, "Code expiré : recommence")
    shared = settings_for(db, SHARED_ID).shared
    client = _jellyfin_client(shared, pending.device)
    if not await client.quick_connect_approved(pending.secret):
        return {"status": "pending"}
    quick_connect.drop(key)
    info = await client.quick_connect_auth(pending.secret)
    own = db.query(UserSettings).filter(UserSettings.jellyfin_user_id == info["user_id"]).first()
    user = db.get(User, own.id) if own else None
    if user is None or not user.active or not user.jellyfin_login:
        # Compte non autorisé : le jeton tout juste créé est aussitôt révoqué
        try:
            await JellyfinClient(shared.jellyfin_url, info["token"], info["user_id"], kind=shared.jellyfin_kind).logout()
        except ServiceError:
            pass
        raise HTTPException(403, "Ce compte Jellyfin n'est pas autorisé à se connecter à SynCiné — demande à l'administrateur")
    return await _jellyfin_session(db, request, response, user, own, info, shared)


# --- Connexion avec Plex ---------------------------------------------------------------


def _client_id(db: Session) -> str:
    shared = settings_for(db, SHARED_ID).shared
    if not shared.plex_client_id:
        shared.plex_client_id = str(uuid.uuid4())
        db.commit()
    return shared.plex_client_id


@router.post("/plex/pin", dependencies=server_only)
async def plex_pin(
    request: Request, response: Response, mode: Literal["link", "window"] = "link", db: Session = Depends(get_db),
):
    """Étape 1 : code plex.tv. Le code est lié à ce navigateur (cookie) : personne d'autre ne peut l'utiliser."""
    shared = settings_for(db, SHARED_ID).shared
    if not (shared.plex_machine_id and shared.plex_client_id):
        raise HTTPException(404, "La connexion avec Plex n'est pas activée sur ce SynCiné")
    keys = guard_attempts(request, trusted=auth.known_device(request) is not None)
    pin_key = f"pin:{auth.client_ip(request)}"
    now = time.monotonic()
    for k in [k for k, (_, exp) in _pending_pins.items() if exp < now]:  # avant le plafond : les codes expirés ne comptent pas
        _pending_pins.pop(k, None)
    if login_limiter.blocked(pin_key) or len(_pending_pins) >= MAX_PENDING_PINS:
        raise HTTPException(429, "Trop d'essais, réessaie dans quelques minutes")
    login_limiter.fail(pin_key)  # chaque code créé compte (appel à plex.tv)
    del keys
    # Retour après connexion : toujours la page de SynCiné (jamais une adresse fournie par le client)
    base = (config.public_url or str(request.base_url)).rstrip("/")
    pin = await plex_auth.create_pin(_client_id(db), mode, f"{base}/plex-done.html" if mode == "window" else None)
    nonce = secrets.token_urlsafe(24)
    _pending_pins[pin["id"]] = (nonce, time.monotonic() + pin["expires_in"])
    response.set_cookie(PIN_COOKIE, nonce, max_age=pin["expires_in"], httponly=True, samesite="lax",
                        secure=auth._is_https(request), path="/api/auth")
    return pin


@router.post("/plex/pin/{pin_id}", dependencies=server_only)
async def plex_check(pin_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    """Étape 2 (interrogée en boucle) : une fois connecté sur plex.tv, vérifie que ce compte Plex est autorisé."""
    pending = _pending_pins.get(pin_id)
    nonce = request.cookies.get(PIN_COOKIE, "")
    if pending is None or not hmac.compare_digest(pending[0], nonce):
        raise HTTPException(410, "Code de connexion Plex expiré — recommence")
    cid = _client_id(db)
    token = await plex_auth.check_pin(cid, pin_id)
    if not token:
        return {"authorized": False}
    _pending_pins.pop(pin_id, None)
    keys = guard_attempts(request, trusted=auth.known_device(request) is not None)
    info = await plex_auth.account_info(cid, token)
    shared = settings_for(db, SHARED_ID).shared

    user = db.query(User).filter(User.plex_user_id == info["id"], User.active.is_(True)).first()
    if user is None and database.setup_required(db) and shared.plex_account_token:
        # Installation d'une base existante : le propriétaire du compte Plex déjà relié devient l'admin
        try:
            owner = await plex_auth.account_info(cid, shared.plex_account_token)
        except ServiceError:
            owner = None
        if owner and owner["id"] == info["id"]:
            user = _first_admin(db)
            user.plex_user_id = info["id"]
            database.setup_code = None
    if user is None:
        login_limiter.fail(*keys)
        raise HTTPException(403, f"Le compte Plex « {info['title']} » n'est pas autorisé sur ce SynCiné — demande à l'administrateur")

    access = await plex_auth.server_access(cid, token, shared.plex_machine_id) if shared.plex_machine_id else None
    if user.id == SHARED_ID:
        # Compte principal : le serveur est déjà relié avec ses jetons, on n'y touche pas
        if not shared.plex_account_token:
            shared.plex_account_token = token
        server_account = 1 if (access is None or access["owned"]) else info["id"]
    else:
        if access is None:
            raise HTTPException(403, "Ce compte Plex n'a pas (ou plus) accès au serveur Plex de l'administrateur")
        own = settings_for(db, user.id).own
        own.plex_account_token = token  # watchlist, vus et notes plex.tv de ce membre
        own.plex_token = access["token"]  # son propre accès au serveur (ses vus, sa progression)
        server_account = 1 if access["owned"] else info["id"]
    user.plex_username, user.plex_thumb = info["title"], info["thumb"]
    if user.plex_server_account_id != server_account:
        user.plex_server_account_id = server_account
        db.commit()
        assign_plex_events(db, server_account, user.id)
    login_limiter.reset(*keys)
    db.commit()  # jetons Plex rafraîchis, même si la 2FA est demandée ensuite
    response.delete_cookie(PIN_COOKIE, path="/api/auth")
    if user.totp_secret:
        return {"authorized": True, **_me(db, None), **_two_factor_ticket(user)}
    auth.open_session(db, user, request, response)
    return {"authorized": True, **_me(db, user)}
