"""Comptes et sessions : mots de passe (scrypt), cookie de session, limitation des essais.

- Le jeton de session n'est jamais stocké en clair (empreinte SHA-256 en base).
- Cookie HttpOnly, SameSite=Lax, Secure quand l'appli est servie en HTTPS.
- Les requêtes qui modifient des données doivent venir de la même origine (voir main.py).
"""

import base64
import hashlib
import hmac
import secrets
import time
from collections import deque
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import config
from app.database import bind_user, get_db
from app.models import AuthSession, User

COOKIE = "cinesync_session"
SESSION_DAYS = 30
PASSWORD_MIN = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


# --- Mots de passe -----------------------------------------------------------------


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(h)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(h)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


# Empreinte factice : le temps de réponse ne révèle pas si l'identifiant existe
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def check_password(user: User | None, password: str) -> bool:
    if user is None or not user.password_hash:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, user.password_hash)


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise HTTPException(422, f"Le mot de passe doit faire au moins {PASSWORD_MIN} caractères")
    if len(password) > 256:
        raise HTTPException(422, "Mot de passe trop long")


def normalize_username(username: str) -> str:
    u = username.strip().lower()
    if not (2 <= len(u) <= 40) or not all(c.isalnum() or c in "._-" for c in u):
        raise HTTPException(422, "Identifiant : 2 à 40 caractères (lettres, chiffres, . _ -)")
    return u


# --- Limitation des essais ---------------------------------------------------------


class RateLimiter:
    """Échecs comptés par clé sur une fenêtre glissante ; la limite dépend du type de clé (préfixe).

    - pair (adresse + identifiant) : quelqu'un qui se trompe de mot de passe -> limite basse ;
    - ip : une adresse qui essaie beaucoup d'identifiants ;
    - user : un identifiant visé depuis beaucoup d'adresses (limite haute : bloquer un compte
      demanderait beaucoup d'essais) ;
    - all : plafond global (attaque répartie).
    """

    LIMITS = {"pair": 8, "ip": 30, "user": 50, "all": 300}
    MAX_KEYS = 10_000

    def __init__(self, window: int):
        self.window = window
        self._fails: dict[str, deque] = {}

    def _count(self, key: str) -> int:
        q = self._fails.get(key)
        if not q:
            return 0
        cutoff = time.monotonic() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            self._fails.pop(key, None)
            return 0
        return len(q)

    def blocked(self, *keys: str) -> bool:
        return any(self._count(k) >= self.LIMITS[k.split(":", 1)[0]] for k in keys)

    def fail(self, *keys: str) -> None:
        if len(self._fails) >= self.MAX_KEYS:  # mémoire bornée : on oublie les plus anciennes clés
            for k in list(self._fails)[: self.MAX_KEYS // 10]:
                self._fails.pop(k, None)
        now = time.monotonic()
        for k in keys:
            self._fails.setdefault(k, deque()).append(now)

    def reset(self, *keys: str) -> None:
        for k in keys:
            if not k.startswith(("all:", "ip:")):  # un succès n'efface pas la trace d'une attaque
                self._fails.pop(k, None)


login_limiter = RateLimiter(window=15 * 60)


def client_ip(request: Request) -> str:
    """Adresse du client. Les en-têtes X-Forwarded-For ne sont lus par uvicorn que s'ils viennent d'un proxy
    de confiance (FORWARDED_ALLOW_IPS) : un client ne peut donc pas se faire passer pour une autre adresse."""
    return request.client.host if request.client else "?"


def guard_attempts(request: Request, username: str = "") -> tuple[str, ...]:
    ip = client_ip(request)
    keys = ("all:", f"ip:{ip}") + ((f"pair:{ip}|{username}", f"user:{username}") if username else ())
    if login_limiter.blocked(*keys):
        raise HTTPException(429, "Trop d'essais, réessaie dans quelques minutes")
    return keys


# --- Sessions ----------------------------------------------------------------------


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_https(request: Request) -> bool:
    # PUBLIC_URL en https : l'appli n'est servie qu'en HTTPS, le cookie ne doit jamais circuler en clair
    if config.public_url.startswith("https://"):
        return True
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=_is_https(request), path="/"
    )


def open_session(db: Session, user: User, request: Request, response: Response) -> None:
    now = datetime.utcnow()
    token = secrets.token_urlsafe(32)
    db.query(AuthSession).filter(AuthSession.expires_at < now).delete()
    db.add(
        AuthSession(
            token_hash=_digest(token), user_id=user.id, expires_at=now + timedelta(days=SESSION_DAYS),
            last_seen_at=now, user_agent=(request.headers.get("user-agent") or "")[:200],
        )
    )
    user.last_login_at = now
    db.commit()
    _set_cookie(request, response, token)


def close_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _digest(token)).delete()
        db.commit()
    response.delete_cookie(COOKIE, path="/")


def close_all_sessions(db: Session, user_id: int, keep_request: Request | None = None) -> None:
    """Déconnecte un compte partout (sauf, éventuellement, la session de cette requête)."""
    q = db.query(AuthSession).filter(AuthSession.user_id == user_id)
    token = keep_request.cookies.get(COOKIE) if keep_request else None
    if token:
        q = q.filter(AuthSession.token_hash != _digest(token))
    q.delete()
    db.commit()


def personal_mode() -> bool:
    return config.cinesync_mode == "personal"


def session_user(db: Session, request: Request, response: Response | None = None) -> User | None:
    if personal_mode():
        # Version personnelle : une seule personne. Sans mot de passe, accès direct ;
        # avec un mot de passe (protection activée dans le Profil), connexion comme en version serveur.
        owner = db.get(User, 1)
        if owner is None or not owner.active:
            return None
        if not owner.password_hash:
            return owner
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    sess = db.get(AuthSession, _digest(token))
    now = datetime.utcnow()
    if sess is None or sess.expires_at < now:
        return None
    user = db.get(User, sess.user_id)
    if user is None or not user.active:
        return None
    # Session glissante : prolongée à l'usage (au plus une écriture par heure)
    if now - sess.last_seen_at > timedelta(hours=1):
        sess.last_seen_at = now
        sess.expires_at = now + timedelta(days=SESSION_DAYS)
        db.commit()
        if response is not None:
            _set_cookie(request, response, token)
    return user


def current_user(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    user = session_user(db, request, response)
    if user is None:
        raise HTTPException(401, "Connexion requise")
    bind_user(db, user.id)
    request.state.user = user
    return user


def require_server_mode() -> None:
    """Fonctions multi-comptes (connexion, comptes de la famille) : absentes de la version personnelle."""
    if personal_mode():
        raise HTTPException(409, "Version personnelle : pas de comptes ni de connexion")


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Réservé à l'administrateur")
    return user


def require_ready(user: User = Depends(current_user)) -> User:
    """Compte utilisable : un mot de passe provisoire doit d'abord être changé."""
    if user.must_change_password and not personal_mode():
        raise HTTPException(403, "Change ton mot de passe provisoire pour continuer")
    return user
