"""Notifications push (Web Push, norme RFC 8030/8291/8292) : les alertes de la cloche arrivent aussi sur
l'écran du téléphone ou de l'ordinateur, même SynCiné fermé (Android, ordinateur ; iPhone : PWA installée).

- Clés VAPID du serveur créées au premier besoin dans DATA_DIR (lisibles par le propriétaire seulement).
- Chaque appareil abonné (PushSubscription) reçoit les notifications de son compte. Les adresses d'envoi
  viennent du navigateur : seuls les services push connus sont acceptés (jamais une adresse quelconque).
- Envoi déclenché à l'enregistrement de toute Notification (événement de session), dans un fil séparé :
  une requête ou une tâche n'attend jamais les services push.
"""

import base64
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import http_ece
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.config import config

log = logging.getLogger(__name__)

# Services push des navigateurs (Chrome/Edge/Android, Firefox, Safari/iOS, Windows)
PUSH_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com")
TTL = 24 * 3600
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="push")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def allowed_endpoint(url: str) -> bool:
    u = urlsplit(url or "")
    host = (u.hostname or "").lower()
    return u.scheme == "https" and not u.username and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


# --- Clés VAPID ----------------------------------------------------------------------


def _vapid_key() -> ec.EllipticCurvePrivateKey:
    path = config.data_dir / "vapid.pem"
    with _lock:
        if not path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
        return serialization.load_pem_private_key(path.read_bytes(), password=None)


def public_key() -> str:
    """Clé publique du serveur (applicationServerKey du navigateur)."""
    pub = _vapid_key().public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(pub)


def _vapid_header(endpoint: str) -> str:
    """En-tête Authorization VAPID : jeton ES256 signé pour le service push visé (RFC 8292)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    u = urlsplit(endpoint)
    sub = config.public_url if config.public_url.startswith("https://") else "https://github.com/GauffrePierre/syncine"
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": sub}
    signing = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode()) + "." + _b64(json.dumps(claims).encode())
    r, s = decode_dss_signature(_vapid_key().sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
    token = signing + "." + _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={token}, k={public_key()}"


# --- Envoi ---------------------------------------------------------------------------------


def encrypt(payload: bytes, p256dh: str, auth: str) -> bytes:
    """Contenu chiffré pour cet appareil seulement (aes128gcm, RFC 8291)."""
    server_key = ec.generate_private_key(ec.SECP256R1())
    return http_ece.encrypt(payload, salt=os.urandom(16), private_key=server_key, dh=_unb64(p256dh), auth_secret=_unb64(auth), version="aes128gcm")


def send(sub, payload: dict, client: httpx.Client) -> int:
    """Envoie à un appareil ; renvoie le code HTTP du service push (404/410 : abonnement expiré)."""
    if not allowed_endpoint(sub.endpoint):
        return 410
    body = encrypt(json.dumps(payload).encode(), sub.p256dh, sub.auth)
    headers = {"Authorization": _vapid_header(sub.endpoint), "Content-Encoding": "aes128gcm", "TTL": str(TTL), "Urgency": "normal"}
    return client.post(sub.endpoint, content=body, headers=headers).status_code


def _link(item: dict, is_admin: bool) -> str:
    if item["kind"] == "service":
        return "/profile"
    if item["kind"] == "request" and is_admin:
        return "/admin?tab=requests"
    return f"/{item['media_type']}/{item['tmdb_id']}" if item["media_type"] and item["tmdb_id"] else "/"


def deliver(items: list[dict]) -> int:
    """Envoie des notifications enregistrées à tous les appareils de leurs destinataires (fil séparé)."""
    from app.database import SessionLocal
    from app.models import PushSubscription, User, UserSettings
    from app.services.messages import render

    sent = 0
    with SessionLocal() as db, httpx.Client(timeout=10.0, follow_redirects=False) as client:
        for item in items:
            subs = db.execute(
                select(PushSubscription).where(PushSubscription.user_id == item["user_id"]).execution_options(all_users=True)
            ).scalars().all()
            if not subs:
                continue
            user = db.get(User, item["user_id"])
            settings = db.get(UserSettings, item["user_id"])
            lang = (settings.ui_language if settings else "") or "fr"
            body = render(item["msg_key"], item["msg_params"], lang) if item["msg_key"] else item["message"]
            payload = {"title": "SynCiné", "body": body, "url": _link(item, bool(user and user.is_admin)), "tag": f"syncine-{item['id']}"}
            for sub in subs:
                try:
                    status = send(sub, payload, client)
                except (httpx.HTTPError, ValueError) as e:
                    log.info("Push : envoi impossible (%s)", e.__class__.__name__)
                    continue
                if status in (404, 410):
                    db.delete(sub)  # appareil désabonné ou abonnement expiré
                elif status < 300:
                    sent += 1
                else:
                    log.info("Push : le service a répondu %s", status)
        db.commit()
    return sent


# --- Déclenchement : chaque Notification enregistrée part aussi en push -----------------


@event.listens_for(Session, "after_flush")
def _collect(session, _ctx):
    from app.models import Notification

    for obj in session.new:
        if isinstance(obj, Notification) and obj.user_id:
            session.info.setdefault("push_items", []).append({
                "id": obj.id, "user_id": obj.user_id, "kind": obj.kind, "media_type": obj.media_type, "tmdb_id": obj.tmdb_id,
                "message": obj.message, "msg_key": obj.msg_key or "", "msg_params": json.loads(obj.msg_params or "{}"),
            })


@event.listens_for(Session, "after_commit")
def _dispatch(session):
    items = session.info.pop("push_items", None)
    if items:
        _executor.submit(_safe_deliver, items)


@event.listens_for(Session, "after_rollback")
def _forget(session):
    session.info.pop("push_items", None)


def _safe_deliver(items: list[dict]) -> None:
    try:
        deliver(items)
    except Exception:  # noqa: BLE001 — l'envoi push ne doit jamais rien casser
        log.exception("Push : échec de l'envoi")
