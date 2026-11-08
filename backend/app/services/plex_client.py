"""Client Plex : bibliothèque, index par id TMDB, images (relayées pour ne pas exposer le token)."""

import asyncio
import hashlib
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

_index_lock = asyncio.Lock()


def _tmdb_id(m: dict) -> int | None:
    for g in m.get("Guid", []) or []:
        gid = g.get("id", "")
        if gid.startswith("tmdb://"):
            try:
                return int(gid[7:])
            except ValueError:
                return None
    guid = m.get("guid", "")  # ancien agent
    if "themoviedb://" in guid:
        try:
            return int(guid.split("themoviedb://")[1].split("?")[0])
        except ValueError:
            return None
    return None


def _image(path: str | None, width: int = 300) -> str | None:
    if not path:
        return None
    return f"/api/plex/image?path={quote(path, safe='')}&width={width}"


class PlexClient:
    is_mock = False

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token.strip()
        # Les réponses dépendent du compte (vus, notes) : le cache est propre à chaque jeton
        self._ns = hashlib.sha256(self.token.encode()).hexdigest()[:12]

    async def _get(self, path: str, ttl: int = 0, **params) -> dict:
        key = ("plex", self.url, self._ns, path, tuple(sorted(params.items())))
        if ttl and (hit := cache.get(key)) is not MISS:
            return hit
        try:
            r = await http().get(
                self.url + path,
                params=params,
                headers={"X-Plex-Token": self.token, "Accept": "application/json"},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise ServiceError("plex", f"Serveur Plex injoignable : {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise ServiceError("plex", "Token Plex invalide", 401)
        if r.status_code >= 400:
            raise ServiceError("plex", f"Erreur Plex ({r.status_code})")
        data = r.json().get("MediaContainer", {})
        if ttl:
            cache.set(key, data, ttl)
        return data

    async def identity(self) -> dict:
        data = await self._get("/identity", ttl=86400)
        return {"machine_id": data.get("machineIdentifier"), "version": data.get("version")}

    def web_url(self, machine_id: str | None, rating_key: str) -> str | None:
        if not machine_id:
            return None
        key = quote(f"/library/metadata/{rating_key}", safe="")
        return f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key={key}"

    async def sections(self) -> list[dict]:
        data = await self._get("/library/sections", ttl=600)
        return [
            {"id": d["key"], "title": d.get("title"), "type": "movie" if d.get("type") == "movie" else "tv"}
            for d in data.get("Directory", [])
            if d.get("type") in ("movie", "show")
        ]

    def _normalize(self, m: dict, section: dict, machine_id: str | None) -> dict:
        added = m.get("addedAt")
        return {
            "rating_key": m.get("ratingKey"),
            "media_type": section["type"],
            "id": _tmdb_id(m),  # id TMDB (peut être None si non apparié)
            "title": m.get("title"),
            "original_title": m.get("originalTitle"),
            "year": m.get("year"),
            "overview": m.get("summary") or "",
            "poster": _image(m.get("thumb"), 342),
            "backdrop": _image(m.get("art"), 1280),
            "added_at": datetime.fromtimestamp(added, timezone.utc).isoformat() if added else None,
            "vote_average": round(float(m.get("audienceRating") or m.get("rating") or 0), 1),
            "content_rating": m.get("contentRating"),
            "duration_min": round(m["duration"] / 60000) if m.get("duration") else None,
            "view_count": m.get("viewCount", 0),
            "user_rating": round(m["userRating"]) if m.get("userRating") is not None else None,  # sur 10
            "last_viewed_at": datetime.fromtimestamp(m["lastViewedAt"], timezone.utc).isoformat() if m.get("lastViewedAt") else None,
            "episodes": m.get("leafCount"),
            "viewed_episodes": m.get("viewedLeafCount"),
            "section": section["title"],
            "section_id": section["id"],
            "plex_url": self.web_url(machine_id, m.get("ratingKey")),
            "in_plex": True,
            "providers": [],
        }

    async def library(self) -> list[dict]:
        """Tous les films et séries, normalisés (cache 10 min)."""
        key = ("plex", "library", self.url, self._ns)
        if (hit := cache.get(key)) is not MISS:
            return hit
        async with _index_lock:
            if (hit := cache.get(key)) is not MISS:
                return hit
            sections, ident = await asyncio.gather(self.sections(), self.identity())
            results = await asyncio.gather(
                *(self._get(f"/library/sections/{s['id']}/all", includeGuids=1) for s in sections)
            )
            items = [
                self._normalize(m, s, ident["machine_id"])
                for s, data in zip(sections, results)
                for m in data.get("Metadata", [])
            ]
            cache.set(key, items, 600)
            return items

    async def index(self) -> dict[tuple[str, int], dict]:
        return {(i["media_type"], i["id"]): i for i in await self.library() if i["id"]}

    async def search(self, query: str, limit: int = 20) -> list[dict]:
        q = query.lower().strip()
        items = await self.library()
        hits = [i for i in items if q in (i["title"] or "").lower() or q in (i["original_title"] or "").lower()]
        hits.sort(key=lambda i: (not (i["title"] or "").lower().startswith(q), i["title"] or ""))
        return hits[:limit]

    async def image(self, path: str, width: int) -> tuple[bytes, str]:
        if not path.startswith("/library/"):
            raise ServiceError("plex", "Chemin d'image invalide", 400)
        height = int(width * 1.5)
        try:
            r = await http().get(
                f"{self.url}/photo/:/transcode",
                params={"url": path, "width": width, "height": height, "minSize": 1, "upscale": 1},
                headers={"X-Plex-Token": self.token},
                timeout=20.0,
            )
        except httpx.HTTPError as e:
            raise ServiceError("plex", "Image Plex indisponible") from e
        if r.status_code >= 400:
            raise ServiceError("plex", "Image Plex indisponible", r.status_code)
        return r.content, r.headers.get("content-type", "image/jpeg")

    async def _action(self, path: str, **params) -> None:
        try:
            r = await http().get(self.url + path, params=params, headers={"X-Plex-Token": self.token}, timeout=15.0)
        except httpx.HTTPError as e:
            raise ServiceError("plex", f"Serveur Plex injoignable : {e.__class__.__name__}") from e
        if r.status_code >= 400:
            raise ServiceError("plex", f"Le serveur Plex a refusé l'action ({r.status_code})")
        cache.clear("plex")

    async def scrobble(self, rating_key: str) -> None:
        """Marque un élément de la bibliothèque comme vu."""
        await self._action("/:/scrobble", key=rating_key, identifier="com.plexapp.plugins.library")

    async def unscrobble(self, rating_key: str) -> None:
        """Marque un élément de la bibliothèque comme non vu."""
        await self._action("/:/unscrobble", key=rating_key, identifier="com.plexapp.plugins.library")

    async def rate(self, rating_key: str, rating10: int) -> None:
        await self._action("/:/rate", key=rating_key, identifier="com.plexapp.plugins.library", rating=rating10)

    async def test(self) -> dict:
        ident = await self.identity()
        sections = await self.sections()
        return {**ident, "sections": len(sections)}
