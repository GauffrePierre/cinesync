"""Connexion : installation (compte admin), identifiant + mot de passe, ou compte Plex autorisé."""

import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

import app.database as database
from app.database import get_db
from app.models import Notification, User
from app.services import auth, messages, plex_auth, totp
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
MAX_PENDING_PINS = 500


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


class TwoFactorIn(BaseModel):
    ticket: str = Field(max_length=100)
    code: str = Field(max_length=20)


class CodeIn(BaseModel):
    code: str = Field(max_length=20)


class RemovePasswordIn(BaseModel):
    current_password: str = Field(max_length=256)


def _me(db: Session, user: User | None) -> dict:
    shared = settings_for(db, SHARED_ID).shared
    return {
        "user": user.to_dict() if user else None,
        "setup_required": database.setup_required(db),
        # Connexion Plex proposée dès que l'admin a relié son serveur (version serveur seulement)
        "plex_login": config.cinesync_mode == "server" and bool(shared.plex_machine_id and shared.plex_client_id),
        # Connexion Jellyfin / Emby proposée dès que l'admin a relié son serveur
        "jellyfin_login": config.cinesync_mode == "server" and bool(shared.jellyfin_url),
        "jellyfin_kind": shared.jellyfin_kind or "jellyfin",
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
        raise HTTPException(409, "SynCiné est déjà installé")
    keys = guard_attempts(request, "setup")  # sujet distinct des identifiants (préfixe login:)
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
    admin.active = True
    login_limiter.reset(*keys)
    database.setup_code = None
    auth.open_session(db, admin, request, response)
    return _me(db, admin)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip().lower()
    q = db.query(User).filter(User.username == username, User.active.is_(True))
    if auth.personal_mode():  # version personnelle : seul le propriétaire se connecte
        q = q.filter(User.id == SHARED_ID)
    user = q.first()
    keys = guard_attempts(request, f"login:{username}", trusted=user is not None and auth.known_device(request) == user.id)
    if not auth.check_password(user, body.password):
        login_limiter.fail(*keys)
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    login_limiter.reset(*keys)
    if user.totp_secret:
        return _two_factor_ticket(user)
    auth.open_session(db, user, request, response)
    return _me(db, user)


# --- Double authentification (2FA) -------------------------------------------------------

_tickets: dict[str, tuple[int, float, int]] = {}  # ticket -> (id du compte, expiration, essais ratés)
TICKET_TTL = 5 * 60


def _two_factor_ticket(user: User) -> dict:
    """Mot de passe (ou Plex) validé, 2FA activée : pas encore de session, un ticket de 5 min pour le code."""
    now = time.monotonic()
    for k in [k for k, (_, exp, _) in _tickets.items() if exp < now]:
        _tickets.pop(k, None)
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = (user.id, now + TICKET_TTL, 0)
    return {"user": None, "two_factor_required": True, "ticket": ticket}


LOCK_AFTER = 10  # codes incorrects d'affilée avant blocage (puis délai doublé à chaque nouvel échec)


def _check_code(db: Session, user: User, code: str) -> bool:
    """Code TOTP (une seule fois chacun) ou code de secours (consommé).

    Mise à jour conditionnelle : deux requêtes simultanées avec le même code ne peuvent pas réussir toutes
    les deux. Les échecs d'affilée sont comptés dans la base (pas seulement par adresse) : après 10, la
    2FA du compte est bloquée 1 min, puis 2, 4… (24 h au plus) et le propriétaire est prévenu."""
    now = datetime.utcnow()
    if user.totp_locked_until and user.totp_locked_until > now:
        raise HTTPException(429, "Trop de codes incorrects : réessaie plus tard")
    ok = False
    clear = {"totp_failures": 0, "totp_locked_until": None}
    counter = totp.verify(user.totp_secret, code, user.totp_last_counter or None)
    if counter is not None:
        q = update(User).where(User.id == user.id, User.totp_last_counter < counter).values(totp_last_counter=counter, **clear)
        ok = db.execute(q).rowcount == 1
    else:
        remaining = totp.use_recovery(code, json.loads(user.recovery_codes or "[]"))
        if remaining is not None:
            q = update(User).where(User.id == user.id, User.recovery_codes == user.recovery_codes).values(recovery_codes=json.dumps(remaining), **clear)
            ok = db.execute(q).rowcount == 1
    if ok:
        db.commit()
        db.refresh(user)
        return True
    user.totp_failures = (user.totp_failures or 0) + 1
    if user.totp_failures >= LOCK_AFTER:
        user.totp_locked_until = now + timedelta(minutes=min(2 ** (user.totp_failures - LOCK_AFTER), 24 * 60))
        if user.totp_failures == LOCK_AFTER:
            db.add(Notification(
                user_id=user.id, kind="service", service="security",
                **messages.fields("Plusieurs codes de double authentification incorrects : si ce n'était pas toi, change ton mot de passe."),
            ))
    db.commit()
    return False


@router.post("/login/2fa")
def login_two_factor(body: TwoFactorIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Deuxième étape de connexion : code de l'application (ou code de secours)."""
    entry = _tickets.get(body.ticket)
    if entry is None or entry[1] < time.monotonic():
        _tickets.pop(body.ticket, None)
        raise HTTPException(410, "Délai dépassé : reconnecte-toi")
    user_id, expires, fails = entry
    user = db.get(User, user_id)
    keys = guard_attempts(request, f"2fa:{user_id}", trusted=auth.known_device(request) == user_id)
    if user is None or not user.active or not _check_code(db, user, body.code):
        login_limiter.fail(*keys)
        if fails + 1 >= 5:
            _tickets.pop(body.ticket, None)  # trop d'essais sur ce ticket : retour à l'identifiant
        else:
            _tickets[body.ticket] = (user_id, expires, fails + 1)
        raise HTTPException(401, "Code incorrect")
    _tickets.pop(body.ticket, None)
    login_limiter.reset(*keys)
    auth.open_session(db, user, request, response)
    return _me(db, user)


class TwoFactorSetupIn(BaseModel):
    password: str = Field("", max_length=256)


RECENT_LOGIN = timedelta(minutes=10)


def _confirm_identity(db: Session, request: Request, user: User, password: str) -> None:
    """Changement sensible : mot de passe actuel exigé ; sans mot de passe (compte Plex), connexion récente."""
    if user.password_hash:
        keys = guard_attempts(request, f"login:{user.username}")
        if not auth.verify_password(password, user.password_hash):
            login_limiter.fail(*keys)
            raise HTTPException(403, "Mot de passe actuel incorrect")
        return
    age = auth.session_age(db, request)
    if age is None or age > RECENT_LOGIN:
        raise HTTPException(403, "Par sécurité, reconnecte-toi puis recommence dans les 10 minutes")


@router.post("/2fa/setup")
def two_factor_setup(request: Request, body: TwoFactorSetupIn | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Étape 1 : nouveau secret (pas encore actif) et QR code à scanner avec l'application."""
    if auth.personal_mode() and not user.password_hash:
        raise HTTPException(409, "Protège d'abord l'accès par un mot de passe")
    if user.totp_secret:  # remplacer le secret passe par la désactivation (code exigé)
        raise HTTPException(409, "La double authentification est déjà activée")
    _confirm_identity(db, request, user, body.password if body else "")
    user.totp_pending = totp.new_secret()
    db.commit()
    uri = totp.provisioning_uri(user.totp_pending, user.username)
    return {"secret": user.totp_pending, "uri": uri, "qr_svg": totp.qr_svg(uri)}


@router.post("/2fa/enable")
def two_factor_enable(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Étape 2 : un premier code juste active la 2FA ; renvoie les codes de secours (affichés une seule fois)."""
    if user.totp_secret:
        raise HTTPException(409, "La double authentification est déjà activée")
    counter = totp.verify(user.totp_pending, body.code)
    if counter is None:
        raise HTTPException(422, "Code incorrect : vérifie l'heure du téléphone et réessaie")
    codes = totp.new_recovery_codes()
    user.totp_secret, user.totp_pending, user.totp_last_counter = user.totp_pending, "", counter
    user.recovery_codes = json.dumps([totp.hash_recovery(c) for c in codes])
    db.commit()
    auth.close_all_sessions(db, user.id, keep_request=request)  # les autres appareils devront passer par le code
    return {**_me(db, user), "recovery_codes": codes}


@router.post("/2fa/disable")
def two_factor_disable(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Désactivation : un code de l'application (ou un code de secours) est exigé."""
    if not user.totp_secret:
        raise HTTPException(409, "La double authentification n'est pas activée")
    keys = guard_attempts(request, f"2fa:{user.id}", trusted=True)
    if not _check_code(db, user, body.code):
        login_limiter.fail(*keys)
        raise HTTPException(403, "Code incorrect")
    user.totp_secret = user.totp_pending = ""
    user.recovery_codes = "[]"
    user.totp_last_counter = user.totp_failures = 0
    db.commit()
    return _me(db, user)


@router.post("/2fa/recovery-codes")
def two_factor_new_codes(body: CodeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Nouveaux codes de secours (les anciens ne marchent plus) ; un code de l'application est exigé."""
    if not user.totp_secret:
        raise HTTPException(409, "La double authentification n'est pas activée")
    keys = guard_attempts(request, f"2fa:{user.id}", trusted=True)
    if not _check_code(db, user, body.code):
        login_limiter.fail(*keys)
        raise HTTPException(403, "Code incorrect")
    codes = totp.new_recovery_codes()
    user.recovery_codes = json.dumps([totp.hash_recovery(c) for c in codes])
    db.commit()
    return {"recovery_codes": codes}


class JellyfinLoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field("", max_length=256)


@router.post("/jellyfin", dependencies=server_only)
async def login_jellyfin(body: JellyfinLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Connexion avec un compte Jellyfin / Emby autorisé par l'administrateur (mot de passe vérifié par le serveur)."""
    from app.models import UserSettings
    from app.services.errors import ServiceError
    from app.services.jellyfin_client import JellyfinClient

    shared = settings_for(db, SHARED_ID).shared
    if not shared.jellyfin_url:
        raise HTTPException(404, "La connexion avec Jellyfin n'est pas activée sur ce SynCiné")
    username = body.username.strip()
    keys = guard_attempts(request, f"jellyfin:{username.lower()}")
    client = JellyfinClient(shared.jellyfin_url, "", "", shared.jellyfin_server_id, shared.jellyfin_public_url, shared.jellyfin_kind)
    try:
        info = await client.authenticate(username, body.password)
    except ServiceError as e:
        if e.status == 401:
            login_limiter.fail(*keys)
            raise HTTPException(401, "Identifiant ou mot de passe incorrect") from e
        raise
    own = db.query(UserSettings).filter(UserSettings.jellyfin_user_id == info["user_id"]).first()
    user = db.get(User, own.id) if own else None
    if user is None or not user.active:
        login_limiter.fail(*keys)
        raise HTTPException(403, "Ce compte Jellyfin n'est pas autorisé sur ce SynCiné — demande à l'administrateur")
    own.jellyfin_token, own.jellyfin_username = info["token"], info["name"]  # jeton du compte : sa bibliothèque, ses vus
    db.commit()
    login_limiter.reset(*keys)
    if user.totp_secret:
        return _two_factor_ticket(user)
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
    if not user.password_hash and not protecting:
        # Compte Plex sans mot de passe : en ajouter un donne un accès durable, connexion récente exigée
        _confirm_identity(db, request, user, "")
    if user.password_hash and not user.must_change_password:
        keys = guard_attempts(request, f"login:{user.username}")
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
    keys = guard_attempts(request, f"login:{user.username}")
    if not auth.verify_password(body.current_password, user.password_hash):
        login_limiter.fail(*keys)
        raise HTTPException(403, "Mot de passe actuel incorrect")
    user.password_hash = ""
    user.must_change_password = False
    if auth.personal_mode():  # accès libre : la double authentification n'aurait plus rien à protéger
        user.totp_secret = user.totp_pending = ""
        user.recovery_codes = "[]"
        user.totp_last_counter = 0
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
    request: Request, response: Response, mode: Literal["link", "window"] = "link", db: Session = Depends(get_db),
):
    """Étape 1 : code plex.tv. Le code est lié à ce navigateur (cookie) : personne d'autre ne peut l'utiliser."""
    shared = settings_for(db, SHARED_ID).shared
    if not (shared.plex_machine_id and shared.plex_client_id):
        raise HTTPException(404, "La connexion avec Plex n'est pas activée sur ce SynCiné")
    keys = guard_attempts(request, trusted=auth.known_device(request) is not None)
    pin_key = f"pin:{auth.client_ip(request)}"
    if login_limiter.blocked(pin_key) or len(_pending_pins) >= MAX_PENDING_PINS:
        raise HTTPException(429, "Trop d'essais, réessaie dans quelques minutes")
    login_limiter.fail(pin_key)  # chaque code créé compte (appel à plex.tv)
    del keys
    # Retour après connexion : toujours la page de SynCiné (jamais une adresse fournie par le client)
    base = (config.public_url or str(request.base_url)).rstrip("/")
    pin = await plex_auth.create_pin(_client_id(db), mode, f"{base}/plex-done.html" if mode == "window" else None)
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
