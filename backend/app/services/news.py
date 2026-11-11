"""Actu Ciné : articles des sites de cinéma et vidéos des chaînes YouTube, par flux RSS.

- Catalogue de sources vérifiées (français et anglais), plus des sources ajoutées par chaque membre :
  adresse d'un flux RSS, d'un site (le flux est trouvé dans la page) ou d'une chaîne YouTube.
- YouTube : flux public de la chaîne ; s'il ne répond pas et qu'une clé API YouTube est réglée par
  l'admin, API officielle (YouTube Data API v3) en secours.
- Les textes sont réduits à du texte brut (jamais de HTML affiché tel quel). Cache de 30 min par flux.
"""

import asyncio
import hashlib
import hmac
import html
import io
import logging
import random
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urljoin, urlsplit

import feedparser

from app.config import config
from app.services import safe_fetch
from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

log = logging.getLogger(__name__)

FEED_TTL = 30 * 60
YT = "https://www.youtube.com/feeds/videos.xml?channel_id="

# Sources vérifiées (flux RSS publics) — lang : langue des articles
CATALOG = [
    {"id": "ecranlarge", "name": "Écran Large", "kind": "site", "lang": "fr", "url": "https://www.ecranlarge.com/feed", "home": "https://www.ecranlarge.com"},
    {"id": "allocine", "name": "AlloCiné", "kind": "site", "lang": "fr", "url": "https://www.allocine.fr/rss/news-cine.xml", "home": "https://www.allocine.fr"},
    {"id": "lemonde", "name": "Le Monde – Cinéma", "kind": "site", "lang": "fr", "url": "https://www.lemonde.fr/cinema/rss_full.xml", "home": "https://www.lemonde.fr/cinema/"},
    {"id": "telerama", "name": "Télérama – Cinéma", "kind": "site", "lang": "fr", "url": "https://www.telerama.fr/rss/cinema.xml", "home": "https://www.telerama.fr/cinema"},
    {"id": "inrocks", "name": "Les Inrocks – Cinéma", "kind": "site", "lang": "fr", "url": "https://www.lesinrocks.com/cinema/feed/", "home": "https://www.lesinrocks.com/cinema/"},
    {"id": "critikat", "name": "Critikat", "kind": "site", "lang": "fr", "url": "https://www.critikat.com/feed/", "home": "https://www.critikat.com"},
    {"id": "lepolyester", "name": "Le Polyester", "kind": "site", "lang": "fr", "url": "https://lepolyester.com/feed/", "home": "https://lepolyester.com"},
    {"id": "jdg-cinema", "name": "Journal du Geek – Cinéma", "kind": "site", "lang": "fr", "url": "https://www.journaldugeek.com/category/cinema/feed/", "home": "https://www.journaldugeek.com"},
    {"id": "indiewire", "name": "IndieWire", "kind": "site", "lang": "en", "url": "https://www.indiewire.com/feed/", "home": "https://www.indiewire.com"},
    {"id": "variety", "name": "Variety – Film", "kind": "site", "lang": "en", "url": "https://variety.com/v/film/feed/", "home": "https://variety.com/v/film/"},
    {"id": "thr", "name": "The Hollywood Reporter", "kind": "site", "lang": "en", "url": "https://www.hollywoodreporter.com/c/movies/feed/", "home": "https://www.hollywoodreporter.com/c/movies/"},
    {"id": "slashfilm", "name": "/Film", "kind": "site", "lang": "en", "url": "https://www.slashfilm.com/feed/", "home": "https://www.slashfilm.com"},
    {"id": "collider", "name": "Collider", "kind": "site", "lang": "en", "url": "https://collider.com/feed/", "home": "https://collider.com"},
    {"id": "lwlies", "name": "Little White Lies", "kind": "site", "lang": "en", "url": "https://www.lwlies.com/feed.rss", "home": "https://www.lwlies.com"},
    {"id": "letterboxd-journal", "name": "Letterboxd Journal", "kind": "site", "lang": "en", "url": "https://letterboxd.com/journal/rss/", "home": "https://letterboxd.com/journal/"},
    {"id": "rogerebert", "name": "RogerEbert.com", "kind": "site", "lang": "en", "url": "https://www.rogerebert.com/feed", "home": "https://www.rogerebert.com"},
]
BY_ID = {s["id"]: s for s in CATALOG}
DEFAULTS = {"fr": ["ecranlarge", "allocine", "lemonde", "telerama"], "en": ["indiewire", "variety", "slashfilm", "letterboxd-journal"]}


# --- Normalisation ----------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def _text(value: str | None, limit: int = 280) -> str:
    s = html.unescape(_TAG.sub(" ", value or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


def _https(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith(("https://", "http://")) else None


def _image(e) -> str | None:
    for m in e.get("media_thumbnail") or []:
        if m.get("url"):
            return _https(m["url"])
    for m in e.get("media_content") or []:
        if m.get("url") and (m.get("medium") == "image" or (m.get("type") or "").startswith("image") or re.search(r"\.(jpe?g|png|webp)", m["url"], re.I)):
            return _https(m["url"])
    for enc in e.get("enclosures") or []:
        if (enc.get("type") or "").startswith("image") and enc.get("href"):
            return _https(enc["href"])
    for field in ("summary", "content"):
        raw = e.get(field)
        if isinstance(raw, list):
            raw = " ".join(c.get("value", "") for c in raw)
        if raw and (m := _IMG.search(raw)):
            return _https(html.unescape(m.group(1)))
    return None


def _date(e) -> str | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat() if t else None


# --- Relais d'images ------------------------------------------------------------------------
# Les images des articles passent par SynCiné : téléchargées une fois (2 à la fois par site, pour respecter
# leurs limites), réduites en WebP et gardées en cache sur le disque. Les sites ne voient pas l'adresse des
# membres, et les téléphones chargent ~30 Ko au lieu de ~300. Seules les adresses signées par le serveur
# (donc venues d'un flux) sont relayées.

IMG_WIDTH = 640
IMG_CACHE_MAX = 300 * 1024 * 1024
_host_locks: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(2))
_decode_lock = asyncio.Semaphore(2)  # décodage d'images : 2 à la fois au plus, quel que soit le site
MAX_PIXELS = 16_000_000
IMAGE_FORMATS = ["JPEG", "PNG", "WEBP", "GIF"]


def _sign(url: str) -> str:
    from app.services.secret import server_secret

    return hmac.new(server_secret(), url.encode(), hashlib.sha256).hexdigest()[:32]


def proxied(url: str | None) -> str | None:
    return f"/api/news/image?u={quote(url, safe='')}&s={_sign(url)}" if url else None


def valid_signature(url: str, sig: str) -> bool:
    return hmac.compare_digest(_sign(url).encode(), (sig or "").encode())


def _cache_dir():
    d = config.data_dir / "cache" / "news-images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune_cache(d) -> None:
    files = sorted(d.glob("*.webp"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    while files and total > IMG_CACHE_MAX:
        f = files.pop(0)
        total -= f.stat().st_size
        f.unlink(missing_ok=True)


def _thumbnail(data: bytes) -> bytes:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(io.BytesIO(data), formats=IMAGE_FORMATS) as im:  # formats courants seulement
        if im.width * im.height > MAX_PIXELS:  # refus net (Pillow ne fait qu'avertir jusqu'au double)
            raise ValueError("image démesurée")
        im.draft("RGB", (IMG_WIDTH * 2, IMG_WIDTH * 2))
        im = im.convert("RGB")
        im.thumbnail((IMG_WIDTH, IMG_WIDTH))
        out = io.BytesIO()
        im.save(out, "WEBP", quality=72, method=4)
        return out.getvalue()


async def image(url: str):
    """Chemin du fichier en cache (créé si besoin) pour une image d'article."""
    d = _cache_dir()
    path = d / (hashlib.sha256(url.encode()).hexdigest()[:40] + ".webp")
    if path.exists():
        return path
    host = urlsplit(url).hostname or ""
    if len(_host_locks) > 1000:  # mémoire bornée
        _host_locks.clear()
    async with _host_locks[host]:
        if path.exists():
            return path
        _, body, ctype = await safe_fetch.fetch(url, timeout=20.0)
        if ctype and not ctype.startswith("image/"):
            raise ServiceError("news", "Ce n'est pas une image", 502)
        try:
            async with _decode_lock:
                data = await asyncio.to_thread(_thumbnail, body)
        except Exception as e:  # noqa: BLE001 — image illisible ou trop grande
            raise ServiceError("news", "Image illisible", 502) from e
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    if random.random() < 0.05:
        await asyncio.to_thread(_prune_cache, d)
    return path


def _items(feed, source: dict) -> list[dict]:
    out = []
    for e in feed.entries[:40]:
        link = _https(e.get("link"))
        if not link or not e.get("title"):
            continue
        video = e.get("yt_videoid")
        out.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16],
            "title": _text(e.get("title"), 200),
            "url": link,
            "summary": _text(e.get("summary") or (e.get("media_description") if video else ""), 280),
            # Vignettes YouTube : servies directement par YouTube ; images d'articles : relayées par SynCiné
            "image": f"https://i.ytimg.com/vi/{video}/hqdefault.jpg" if video else proxied(_image(e)),
            "published": _date(e),
            "kind": "video" if video or source["kind"] == "youtube" else "article",
            "source": source["id"],
            "source_name": source["name"],
        })
    return out


# --- Lecture des flux --------------------------------------------------------------------


async def _get_feed(url: str, trusted: bool):
    if trusted:
        try:
            r = await http().get(url, timeout=15.0)
        except Exception as e:  # noqa: BLE001 — réseau : une source en panne ne bloque pas les autres
            raise ServiceError("news", f"Site injoignable : {e.__class__.__name__}", 502) from e
        if r.status_code >= 400:
            raise ServiceError("news", f"Le site a répondu {r.status_code}", 502)
        body = r.content
    else:
        _, body, _ = await safe_fetch.fetch(url)
    feed = feedparser.parse(body)
    if not feed.entries:
        raise ServiceError("news", "Aucun article dans ce flux", 502)
    return feed


async def _youtube_api(channel_id: str, source: dict, api_key: str) -> list[dict]:
    """Secours : 15 dernières vidéos d'une chaîne via l'API officielle (2 unités de quota)."""
    uploads = "UU" + channel_id[2:]
    try:
        r = await http().get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet", "playlistId": uploads, "maxResults": 15, "key": api_key},
            timeout=15.0,
        )
    except Exception as e:  # noqa: BLE001
        raise ServiceError("news", f"API YouTube injoignable : {e.__class__.__name__}", 502) from e
    if r.status_code >= 400:
        raise ServiceError("news", f"API YouTube : erreur {r.status_code}", 502)
    out = []
    for it in r.json().get("items", []):
        sn = it.get("snippet") or {}
        vid = (sn.get("resourceId") or {}).get("videoId")
        if not vid:
            continue
        thumbs = sn.get("thumbnails") or {}
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        link = f"https://www.youtube.com/watch?v={vid}"
        out.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:16], "title": _text(sn.get("title"), 200), "url": link,
            "summary": _text(sn.get("description"), 280), "image": thumb, "published": sn.get("publishedAt"),
            "kind": "video", "source": source["id"], "source_name": source["name"],
        })
    return out


async def source_items(source: dict, youtube_key: str = "") -> list[dict]:
    key = ("news", source["url"])
    if (hit := cache.get(key)) is not MISS:
        return hit
    try:
        items = _items(await _get_feed(source["url"], trusted=source["id"] in BY_ID), source)
    except ServiceError:
        channel = parse_qs(urlsplit(source["url"]).query).get("channel_id", [None])[0]
        if source["kind"] == "youtube" and channel and youtube_key:
            items = await _youtube_api(channel, source, youtube_key)
        else:
            raise
    cache.set(key, items, FEED_TTL)
    return items


async def gather(sources: list[dict], youtube_key: str = "") -> tuple[list[dict], dict[str, str]]:
    """Articles de toutes les sources, du plus récent au plus ancien ; erreurs par source."""
    results = await asyncio.gather(*(source_items(s, youtube_key) for s in sources), return_exceptions=True)
    items, errors = [], {}
    for s, r in zip(sources, results):
        if isinstance(r, ServiceError):
            errors[s["id"]] = r.message
        elif isinstance(r, Exception):
            log.warning("Actu Ciné %s : %s", s["id"], r)
            errors[s["id"]] = f"Erreur inattendue : {r.__class__.__name__}"
        else:
            items += r
    seen, unique = set(), []
    for it in sorted(items, key=lambda i: i["published"] or "", reverse=True):
        if it["url"] not in seen:
            seen.add(it["url"])
            unique.append(it)
    return unique, errors


# --- Sources personnelles ----------------------------------------------------------------


_CHANNEL = re.compile(r"(UC[\w-]{22})")


async def resolve(url: str, youtube_key: str = "") -> dict:
    """Adresse saisie par un membre -> source {id, name, url, kind, home}.
    Accepte : flux RSS/Atom, page d'un site (flux annoncé dans la page), chaîne YouTube."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    u = urlsplit(url)
    host = (u.hostname or "").lower()

    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):  # nom exact (pas « evilyoutube.com »)
        channel = next(iter(_CHANNEL.findall(u.path) or _CHANNEL.findall(parse_qs(u.query).get("channel_id", [""])[0])), None)
        if not channel:
            # Adresse @nom : l'identifiant de la chaîne figure dans la page
            _, body, _ = await safe_fetch.fetch(url)
            text = body.decode("utf-8", "ignore")
            m = re.search(r'"externalId":"(UC[\w-]{22})"', text) or re.search(r"channel_id=(UC[\w-]{22})", text)
            if not m:
                raise ServiceError("news", "Chaîne YouTube introuvable : utilise l'adresse youtube.com/channel/UC…", 422)
            channel = m.group(1)
        feed_url = YT + channel
        source = {"id": "yt:" + channel, "name": "YouTube", "kind": "youtube", "url": feed_url, "home": f"https://www.youtube.com/channel/{channel}"}
        try:
            feed = await _get_feed(feed_url, trusted=False)
            source["name"] = (feed.feed.get("title") or "YouTube")[:80]
        except ServiceError:
            if not youtube_key:
                raise ServiceError("news", "YouTube ne fournit pas le flux de cette chaîne pour le moment ; l'admin peut ajouter une clé API YouTube (Actu Ciné → Sources)", 502)
            items = await _youtube_api(channel, source, youtube_key)
            if not items:
                raise ServiceError("news", "Aucune vidéo trouvée sur cette chaîne", 422)
        return source

    final, body, ctype = await safe_fetch.fetch(url)
    feed = feedparser.parse(body)
    feed_url = final
    if not feed.entries:
        # Page d'un site : on cherche le flux qu'elle annonce
        text = body.decode("utf-8", "ignore")
        links = re.findall(r"<link[^>]+type=[\"']application/(?:rss|atom)\+xml[\"'][^>]*>", text, re.I)
        hrefs = [m.group(1) for lk in links if (m := re.search(r"href=[\"']([^\"']+)[\"']", lk))]
        if not hrefs:
            raise ServiceError("news", "Aucun flux d'articles (RSS) trouvé à cette adresse", 422)
        feed_url = urljoin(final, html.unescape(hrefs[0]))
        _, body, _ = await safe_fetch.fetch(feed_url)
        feed = feedparser.parse(body)
        if not feed.entries:
            raise ServiceError("news", "Le flux trouvé ne contient aucun article", 422)
    name = _text(feed.feed.get("title"), 80) or urlsplit(feed_url).hostname
    return {"id": "rss:" + hashlib.sha1(feed_url.encode()).hexdigest()[:12], "name": name, "kind": "site", "url": feed_url,
            "home": _https(feed.feed.get("link")) or f"https://{urlsplit(feed_url).hostname}"}
