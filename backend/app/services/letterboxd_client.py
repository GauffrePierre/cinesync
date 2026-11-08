"""Letterboxd via le flux RSS public (pas d'OAuth, juste le nom d'utilisateur)."""

import re

import feedparser
import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

_IMG = re.compile(r'<img src="([^"]+)"')


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class LetterboxdClient:
    def __init__(self, username: str):
        self.username = username.strip().lstrip("@")

    async def diary(self) -> list[dict]:
        key = ("letterboxd", self.username)
        if (hit := cache.get(key)) is not MISS:
            return hit
        url = f"https://letterboxd.com/{self.username}/rss/"
        try:
            r = await http().get(url, timeout=30.0)
        except httpx.HTTPError as e:
            raise ServiceError("letterboxd", f"Letterboxd injoignable : {e.__class__.__name__}") from e
        if r.status_code == 404:
            raise ServiceError("letterboxd", f"Utilisateur Letterboxd « {self.username} » introuvable", 404)
        if r.status_code == 403:
            raise ServiceError("letterboxd", "Letterboxd refuse l'accès au flux RSS depuis ce serveur (403)", 403)
        if r.status_code >= 400:
            raise ServiceError("letterboxd", f"Erreur Letterboxd ({r.status_code})")

        feed = feedparser.parse(r.text)
        out = []
        for e in feed.entries:
            title = e.get("letterboxd_filmtitle")
            if not title:  # listes, etc.
                continue
            rating = e.get("letterboxd_memberrating")
            poster = _IMG.search(e.get("summary", "") or "")
            out.append(
                {
                    "tmdb_id": _int(e.get("tmdb_movieid")),
                    "media_type": "movie",
                    "title": title,
                    "year": _int(e.get("letterboxd_filmyear")),
                    "rating": float(rating) if rating else None,  # sur 5
                    "watched_date": e.get("letterboxd_watcheddate"),
                    "rewatch": e.get("letterboxd_rewatch") == "Yes",
                    "url": e.get("link"),
                    "poster": poster.group(1) if poster else None,
                }
            )
        cache.set(key, out, 1800)
        return out

    async def test(self) -> dict:
        return {"entries": len(await self.diary())}
