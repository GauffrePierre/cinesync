"""Actu Ciné : lecture des flux, texte brut uniquement, adresses privées refusées, sources vérifiées."""

import asyncio

import feedparser
import pytest

from app.services import news, safe_fetch
from app.services.errors import ServiceError
from tests.test_accounts import add_member, client, fresh, login, setup_admin  # noqa: F401

RSS = """<?xml version="1.0"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Ciné Test</title><link>https://cine.example</link>
<item><title>Dune &amp; co</title><link>https://cine.example/dune</link><pubDate>Sat, 08 Nov 2026 10:00:00 GMT</pubDate>
<description><![CDATA[<p>Critique <b>enthousiaste</b><script>alert(1)</script><img src="https://cine.example/dune.jpg"></p>]]></description></item>
<item><title>Ancien</title><link>https://cine.example/old</link><pubDate>Fri, 07 Nov 2026 10:00:00 GMT</pubDate>
<media:thumbnail url="https://cine.example/old.jpg"/></item>
</channel></rss>""".encode()

YT = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/">
<title>Chaîne Test</title><entry><yt:videoId>abc123</yt:videoId><title>Analyse</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
<published>2026-11-08T09:00:00+00:00</published><media:group><media:description>Une vidéo</media:description></media:group></entry></feed>""".encode()


def test_articles_are_plain_text_with_images():
    items = news._items(feedparser.parse(RSS), {"id": "t", "name": "Ciné Test", "kind": "site"})
    first = items[0]
    assert first["title"] == "Dune & co"
    # Image relayée par SynCiné, avec une adresse signée
    assert first["image"].startswith("/api/news/image?u=https%3A%2F%2Fcine.example%2Fdune.jpg&s=")
    # Texte brut uniquement : balises retirées, scripts supprimés avec leur contenu
    assert first["summary"] == "Critique enthousiaste"
    assert "old.jpg" in items[1]["image"] and first["kind"] == "article"


def test_youtube_entries_are_videos_with_thumbnail():
    items = news._items(feedparser.parse(YT), {"id": "yt:x", "name": "Chaine", "kind": "youtube"})
    assert items[0]["kind"] == "video" and items[0]["image"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"


@pytest.mark.parametrize("url", ["http://127.0.0.1/feed", "http://192.168.1.10:8080/rss", "http://10.0.0.1", "http://[::1]/", "file:///etc/passwd",
                                 "http://169.254.169.254/latest", "https://user:pw@example.com/"])
def test_private_or_odd_addresses_are_refused(url):
    with pytest.raises(ServiceError):
        asyncio.run(safe_fetch.check_url(url))


def test_sources_default_then_custom_only_if_verified(fresh, monkeypatch):  # noqa: F811
    admin = client()
    setup_admin(admin)
    cat = admin.get("/api/news/catalog").json()
    assert [s["id"] for s in cat["active"]] == news.DEFAULTS["fr"]
    # Une source personnelle inconnue envoyée directement est ignorée (pas d'adresse arbitraire)
    r = admin.put("/api/news/sources", json={"sources": [{"id": "ecranlarge"}, {"id": "rss:evil", "url": "http://10.0.0.1/rss"}]}).json()
    assert [s["id"] for s in r["active"]] == ["ecranlarge"]

    async def fake_resolve(url, key=""):
        return {"id": "rss:abc", "name": "Mon blog", "kind": "site", "url": "https://blog.example/feed", "home": "https://blog.example"}

    monkeypatch.setattr(news, "resolve", fake_resolve)
    r = admin.post("/api/news/sources/custom", json={"url": "https://blog.example"}).json()
    assert [s["id"] for s in r["active"]] == ["ecranlarge", "rss:abc"]
    # Chaque membre a ses propres sources
    add_member(admin)
    alice = login("alice", "provisoire1")
    alice.post("/api/auth/password", json={"new_password": "nouveau-mdp-alice"})
    assert [s["id"] for s in alice.get("/api/news/catalog").json()["active"]] == news.DEFAULTS["fr"]


def test_image_relay_only_serves_signed_addresses(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    url = "http://10.0.0.1/secret.png"
    assert admin.get("/api/news/image", params={"u": url, "s": "faux"}).status_code == 403
    # Même signée, une adresse privée est refusée par le téléchargement sûr
    assert admin.get("/api/news/image", params={"u": url, "s": news._sign(url)}).status_code == 422
    assert client().get("/api/news/image", params={"u": url, "s": news._sign(url)}).status_code == 401


def test_dns_rebinding_is_blocked_at_connection_time(monkeypatch):
    """Le nom pointe vers une adresse publique à la vérification, puis vers le réseau local à la connexion."""
    calls = {"n": 0}

    async def rebinding(self, host, port, *a, **k):
        calls["n"] += 1
        ip = "93.184.215.14" if calls["n"] == 1 else "127.0.0.1"
        return [(2, 1, 6, "", (ip, port))]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", rebinding)
    with pytest.raises(ServiceError):
        asyncio.run(safe_fetch.fetch("http://rebind.example/feed"))
    assert calls["n"] >= 2  # la vérification est bien refaite à la connexion


def test_waiting_requests_do_not_hold_database_connections(fresh, monkeypatch, tmp_path):  # noqa: F811
    """Une requête qui attend un service extérieur ne doit pas garder de connexion à la base (sinon un
    afflux d'images à relayer bloque toute l'appli)."""
    from app.database import engine

    admin = client()
    setup_admin(admin)
    seen = []
    img = tmp_path / "x.webp"
    img.write_bytes(b"RIFF0000WEBP")

    async def slow_image(url):
        seen.append(engine.pool.checkedout())
        return img

    monkeypatch.setattr(news, "image", slow_image)
    url = "https://cine.example/x.jpg"
    assert admin.get("/api/news/image", params={"u": url, "s": news._sign(url)}).status_code == 200
    assert seen == [0]


def test_api_keys_never_logged():
    import logging

    import app.main  # noqa: F401

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


# --- Revue de sécurité : réponses piégées ------------------------------------------------


def _serve(monkeypatch, body: bytes, headers: dict):
    import httpx

    from app.services import safe_fetch

    async def ok(url):
        return url

    monkeypatch.setattr(safe_fetch, "check_url", ok)
    monkeypatch.setattr(safe_fetch, "_transport", lambda: httpx.MockTransport(lambda req: httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))))


def test_gzip_bomb_is_stopped_at_the_decompressed_size(monkeypatch):
    import asyncio
    import gzip

    from app.services import safe_fetch
    from app.services.errors import ServiceError

    bomb = gzip.compress(b"\0" * (200 * 1024 * 1024))  # ~200 Ko compressés -> 200 Mo
    _serve(monkeypatch, bomb, {"content-encoding": "gzip"})
    with pytest.raises(ServiceError, match="volumineuse"):
        asyncio.run(safe_fetch.fetch("https://example.org/feed"))
    _serve(monkeypatch, gzip.compress(bomb), {"content-encoding": "gzip, gzip"})
    with pytest.raises(ServiceError, match="Encodage"):
        asyncio.run(safe_fetch.fetch("https://example.org/feed"))
    _serve(monkeypatch, gzip.compress(b"<rss/>"), {"content-encoding": "gzip"})
    assert asyncio.run(safe_fetch.fetch("https://example.org/feed"))[1] == b"<rss/>"


def test_oversized_or_exotic_images_are_refused():
    import io

    from PIL import Image

    from app.services import news

    big = io.BytesIO()
    Image.new("1", (5000, 4000)).save(big, "PNG")  # 20 Mpx, fichier minuscule
    with pytest.raises(Exception):
        news._thumbnail(big.getvalue())
    tiff = io.BytesIO()
    Image.new("RGB", (10, 10)).save(tiff, "TIFF")
    with pytest.raises(Exception):
        news._thumbnail(tiff.getvalue())
    ok = io.BytesIO()
    Image.new("RGB", (800, 600)).save(ok, "JPEG")
    assert news._thumbnail(ok.getvalue())[:4] == b"RIFF"


def test_wrapped_private_addresses_and_odd_signatures():
    from app.services import news, safe_fetch

    assert not safe_fetch._public("64:ff9b::7f00:1")  # 127.0.0.1 via NAT64
    assert not safe_fetch._public("::192.168.1.1")
    assert safe_fetch._public("64:ff9b::808:808")  # 8.8.8.8
    assert not news.valid_signature("https://example.org/a.jpg", "é" * 32)  # pas d'erreur 500
