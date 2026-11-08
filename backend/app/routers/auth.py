"""Connexion : installation (compte admin), identifiant + mot de passe, ou compte Plex autorisé."""

import hmac
import secrets
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import app.database as database
from app.database import get_db
from app.models import User
from app.services import auth, plex_auth
from app.config import config
from app.services.auth import current_user, guard_attempts, login_limiter, require_server_mode
from app.services.context import SHARED_ID, settings_for
from app.services.errors import ServiceError
from app.services.history import assign_plex_events

router = APIRouter(prefix="/auth", tags=["auth"])
# Connexion, installation, mot de passe : seulement dans la version serveur
server_only = [Depends(require_server_mode)]

PIN_COOKIE = "cinesync_plex_pin"
_pending_pins: dict[int, tuple[str, float]] = {}  # pin plex.tv -> (jeton du navigateur, expiration)


class SetupIn(BaseModel):
    code: str = Field(max_length=40)
    username: str = Field(max_length=40)
    password: str = Field(max_length=256)
    display_name: str = Field("", max_length=60)


class LoginIn(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field("", max_length=256)
    new_password: str = Field(max_length=256)


class ProfileIn(BaseModel):
    display_name: str = Field(max_length=60)
    username: str | None = Field(None, max_length=40)


class RemovePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)


def _me(db: Session, user: User | None) -> dict:
    shared = settings_for(db, SHARED_ID).shared
    return {
        "user": user.to_dict() if user else None,
        "setup_required": database.setup_required(db),
        # Connexion Plex proposée dès que l'admin a relié son serveur (version serveur seulement)
        "plex_login": config.cinesync_mode == "server" and bool(shared.plex_machine_id and shared.plex_client_id),
        "mode": config.cinesync_mode,
    }


def _first_admin(db: Session) -> User:
    admin = db.query(User).filter(User.role == "admin").order_by(User.id).first()
    if admin is None:
        admin = User(id=SHARED_ID, username="admin", role="admin")
        db.add(admin)
        db.flush()
    return admin


@router.get("/me")
def me(request: Request, response: Response, db: Session = Depends(get_db)):
    return _me(db, auth.session_user(db, request, response))


@router.post("/setup", dependencies=server_only)
def setup(body: SetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Création du compte administrateur, avec le code affiché dans les journaux du conteneur."""
    if not database.setup_required(db):
        raise HTTPException(409, "CinéSync est déjà installé")
    keys = guard_attempts(request, "setup")
    expected = (database.setup_code or "").replace("-", "")
    given = body.code.strip().upper().replace("-", "").replace(" ", "")
    if not expected or not hmac.compare_digest(given, expected):
        login_limiter.fail(*keys)
        raise HTTPException(403, "Code d'installation incorrect — il est affiché dans les journaux du conteneur cinesync-backend")
    username = auth.normalize_username(body.username)
    auth.validate_password(body.password)
    admin = _first_admin(db)
    if db.query(User).filter(User.username == username, User.id != admin.id).first():
        raise HTTPException(409, "Cet identifiant est déjà pris")
    admin.username, admin.password_hash = username, auth.hash_password(body.password)
    admin.display_name = body.display_name.strip()
    admin.must_change_password = False
    login_limiter.reset(*keys)
    database.setup_code = None
    auth.open_session(db, admin, request, response)
    return _me(db, admin)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    keys = guard_attempts(request, username)
    user = db.query(User).filter(User.username == username, User.active.is_(True)).first()
    if not auth.check_password(user, body.password):
        login_limiter.fail(*keys)
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    login_limiter.reset(*keys)
    auth.open_session(db, user, request, response)
    return _me(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.close_session(db, request, response)
    return {"ok": True}


@router.post("/password")
def change_password(body: PasswordIn, request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Nouveau mot de passe. L'actuel est demandé, sauf juste après une connexion avec un mot de passe provisoire.
    Version personnelle : le premier mot de passe active la protection de l'accès (et ouvre une session)."""
    protecting = auth.personal_mode() and not user.password_hash
    if user.password_hash and not user.must_change_password:
        keys = guard_attempts(request, user.username)
        if not auth.verify_password(body.current_password, user.password_hash):
            login_limiter.fail(*keys)
            raise HTTPException(403, "Mot de passe actuel incorrect")
    auth.validate_password(body.new_password)
    if user.password_hash and auth.verify_password(body.new_password, user.password_hash):
        raise HTTPException(422, "Choisis un mot de passe différent de l'actuel")
    user.password_hash = auth.hash_password(body.new_password)
    user.must_change_password = False
    db.commit()
    auth.close_all_sessions(db, user.id, keep_request=request)  # déconnecte les autres appareils
    if protecting:
        auth.open_session(db, user, request, response)  # cet appareil reste connecté
    return _me(db, user)


@router.delete("/password")
def remove_password(body: RemovePasswordIn, request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Supprime le mot de passe. Version personnelle : l'accès redevient libre. Version serveur : seulement
    pour un compte qui peut encore se connecter avec Plex (sinon il ne pourrait plus se connecter)."""
    if not user.password_hash:
        raise HTTPException(409, "Aucun mot de passe à supprimer")
    if not auth.personal_mode() and not user.plex_user_id:
        raise HTTPException(409, "Ce compte se connecte uniquement par mot de passe : il ne peut pas être supprimé")
    keys = guard_attempts(request, user.username)
    if not auth.verify_password(body.current_password, user.password_hash):
        login_limiter.fail(*keys)
        raise HTTPException(403, "Mot de passe actuel incorrect")
    user.password_hash = ""
    user.must_change_password = False
    db.commit()
    if auth.personal_mode():  # accès libre : les sessions n'ont plus d'objet
        auth.close_all_sessions(db, user.id)
        response.delete_cookie(auth.COOKIE, path="/")
    return _me(db, user)


@router.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.display_name = body.display_name.strip()
    if body.username is not None and body.username.strip().lower() != user.username:
        username = auth.normalize_username(body.username)
        if db.query(User).filter(User.username == username, User.id != user.id).first():
            raise HTTPException(409, "Cet identifiant est déjà pris")
        user.username = username
    db.commit()
    return _me(db, user)


# --- Connexion avec Plex ---------------------------------------------------------------


def _client_id(db: Session) -> str:
    shared = settings_for(db, SHARED_ID).shared
    if not shared.plex_client_id:
        shared.plex_client_id = str(uuid.uuid4())
        db.commit()
    return shared.plex_client_id


@router.post("/plex/pin", dependencies=server_only)
async def plex_pin(
    request: Request, response: Response, mode: Literal["link", "window"] = "link", forward_url: str | None = None,
    db: Session = Depends(get_db),
):
    """Étape 1 : code plex.tv. Le code est lié à ce navigateur (cookie) : personne d'autre ne peut l'utiliser."""
    guard_attempts(request)
    pin = await plex_auth.create_pin(_client_id(db), mode, forward_url)
    nonce = secrets.token_urlsafe(24)
    now = time.monotonic()
    for k in [k for k, (_, exp) in _pending_pins.items() if exp < now]:
        _pending_pins.pop(k, None)
    _pending_pins[pin["id"]] = (nonce, now + pin["expires_in"])
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
    keys = guard_attempts(request)
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
        raise HTTPException(403, f"Le compte Plex « {info['title']} » n'est pas autorisé sur ce CinéSync — demande à l'administrateur")

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
    auth.open_session(db, user, request, response)
    response.delete_cookie(PIN_COOKIE, path="/api/auth")
    return {"authorized": True, **_me(db, user)}
