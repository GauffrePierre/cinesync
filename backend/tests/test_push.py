"""Notifications push : chiffrement, signature VAPID, liste blanche des services, abonnements, envoi."""

import base64
import json

import http_ece
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from app.services import messages, push
from tests.test_accounts import client, fresh, link_plex, member, setup_admin  # noqa: F401 (fixture)

FCM = "https://fcm.googleapis.com/fcm/send/abc123"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _device():
    """Clés d'un navigateur abonné."""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = b"0123456789abcdef"
    return key, {"p256dh": _b64(pub), "auth": _b64(auth)}, auth


def test_payload_is_readable_only_by_the_device():
    key, keys, auth = _device()
    body = push.encrypt(b'{"body":"Bonjour"}', keys["p256dh"], keys["auth"])
    assert b"Bonjour" not in body
    assert http_ece.decrypt(body, private_key=key, auth_secret=auth, version="aes128gcm") == b'{"body":"Bonjour"}'


def test_vapid_token_is_signed_by_the_server_key(fresh):  # noqa: F811
    header = push._vapid_header(FCM)
    token = header.split("t=")[1].split(",")[0]
    k = header.split("k=")[1]
    head, claims, sig = token.split(".")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    assert json.loads(pad(claims))["aud"] == "https://fcm.googleapis.com"
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pad(k))
    raw = pad(sig)
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")), f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert k == push.public_key()


def test_only_known_push_services_are_accepted():
    assert push.allowed_endpoint(FCM)
    assert push.allowed_endpoint("https://web.push.apple.com/QGuQyavXutnMH")
    assert push.allowed_endpoint("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert not push.allowed_endpoint("http://fcm.googleapis.com/x")  # pas https
    assert not push.allowed_endpoint("https://192.168.1.1/x")
    assert not push.allowed_endpoint("https://fcm.googleapis.com.evil.example/x")
    assert not push.allowed_endpoint("https://user@fcm.googleapis.com/x")


def test_subscriptions_follow_the_signed_in_account(fresh):  # noqa: F811
    _, keys, _ = _device()
    admin = client()
    setup_admin(admin)
    assert admin.post("/api/push/subscribe", json={"endpoint": "https://nas.local/push", "keys": keys}).status_code == 422
    assert admin.post("/api/push/subscribe", json={"endpoint": FCM, "keys": keys}).status_code == 200
    assert admin.get("/api/push/config").json()["devices"] == 1
    # Même appareil, autre compte connecté : l'abonnement passe à ce compte (plus rien pour l'admin)
    alice = member(admin, "alice")
    assert alice.post("/api/push/subscribe", json={"endpoint": FCM, "keys": keys}).status_code == 200
    assert admin.get("/api/push/config").json()["devices"] == 0
    assert alice.get("/api/push/config").json()["devices"] == 1
    assert alice.post("/api/push/unsubscribe", json={"endpoint": FCM}).status_code == 200
    assert alice.get("/api/push/config").json()["devices"] == 0


def test_notifications_are_pushed_in_the_recipient_language(fresh, monkeypatch):  # noqa: F811
    key, keys, auth = _device()
    sent = []

    def handler(req: httpx.Request):
        assert req.headers["content-encoding"] == "aes128gcm" and req.headers["authorization"].startswith("vapid t=")
        sent.append(json.loads(http_ece.decrypt(req.content, private_key=key, auth_secret=auth, version="aes128gcm")))
        return httpx.Response(201)

    real_client = httpx.Client
    monkeypatch.setattr(push.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    admin = client()
    setup_admin(admin)
    admin.put("/api/settings", json={"ui_language": "en"})
    admin.post("/api/push/subscribe", json={"endpoint": FCM, "keys": keys})
    alice = member(admin, "alice")
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        link_plex(db.query(User).filter(User.username == "alice").one().id)
    assert alice.post("/api/requests", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).status_code == 200
    push._executor.submit(lambda: None).result()  # attend l'envoi (fil séparé)
    assert sent == [{"title": "SynCiné", "body": "Alice is requesting “Matrix”", "url": "/admin?tab=requests", "tag": sent[0]["tag"]}]
    # Abonnement expiré côté service push : supprimé
    monkeypatch.setattr(push.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(410))))
    alice.post("/api/requests", json={"tmdb_id": 604, "media_type": "movie", "title": "Matrix Reloaded"})
    push._executor.submit(lambda: None).result()
    assert admin.get("/api/push/config").json()["devices"] == 0


def test_templates_are_translated_in_the_interface_too():
    from pathlib import Path

    en = "".join(p.read_text() for p in Path(__file__).resolve().parents[2].glob("frontend/src/i18n/en/*.js"))
    for key in messages.TEMPLATES:
        assert key.replace("'", "\\'") in en or key in en, f"Traduction manquante dans l'interface : {key}"
    assert messages.render("{title} est maintenant disponible sur {platforms}", {"title": "Dune", "platforms": "Netflix"}, "en") == "Dune is now available on Netflix"
