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
    # Image relayée par CinéSync, avec une adresse signée
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
