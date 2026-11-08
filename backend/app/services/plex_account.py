"""Données personnelles du compte plex.tv : watchlist, vu, notes (indépendamment d'un serveur).

- Watchlist : discover.provider.plex.tv (lecture, ajout, retrait).
- Vu / notes d'un titre absent de ta bibliothèque : metadata.provider.plex.tv.
- Correspondance id TMDB -> identifiant Plex : /library/metadata/matches.
"""

import asyncio
import logging

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

log = logging.getLogger(__name__)

DISCOVER = "https://discover.provider.plex.tv"
METADATA = "https://metadata.provider.plex.tv"


def tmdb_from_guids(m: dict) -> int | None:
    for g in m.get("Guid", []) or []:
        gid = g.get("id", "")
        if gid.startswith("tmdb://"):
            try:
                return int(gid[7:])
            except ValueError:
                return None
    return None


class PlexAccount:
    def __init__(self, token: str, client_id: str):
        self.token = token
        self.client_id = client_id

    def _headers(self) -> dict:
        return {
            "Accept": "application/json",
            "X-Plex-Token": self.token,
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Product": "CineSync",
        }

    async def _req(self, method: str, url: str, **params) -> dict:
        try:
            r = await http().request(method, url, params=params, headers=self._headers(), timeout=30.0)
        except httpx.HTTPError as e:
            raise ServiceError("plex", f"plex.tv injoignable : {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise ServiceError("plex", "Session plex.tv expirée — reconnecte-toi dans le Profil", 401)
        if r.status_code >= 400:
            raise ServiceError("plex", f"Erreur plex.tv ({r.status_code})")
        try:
            return r.json() if r.content else {}
        except ValueError:
            return {}

    # --- Lecture -----------------------------------------------------------------

    async def watchlist(self) -> list[dict]:
        """Toute la watchlist Plex (paginée par 100)."""
        out, start, total = [], 0, None
        while total is None or start < total:
            data = await self._req(
                "GET",
                f"{DISCOVER}/library/sections/watchlist/all",
                includeGuids=1,
                sort="watchlistedAt:desc",  # du plus récent au plus ancien
                **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": 100},
            )
            mc = data.get("MediaContainer", {})
            total = mc.get("totalSize", 0)
            items = mc.get("Metadata", []) or []
            for m in items:
                tid = tmdb_from_guids(m)
                if not tid or m.get("type") not in ("movie", "show"):
                    continue
                out.append(
                    {
                        "tmdb_id": tid,
                        "media_type": "movie" if m["type"] == "movie" else "tv",
                        "title": m.get("title"),
                        "year": m.get("year"),
                        "poster": m.get("thumb") if (m.get("thumb") or "").startswith("http") else None,
                        "plex_key": m.get("ratingKey"),
                    }
                )
            if not items:
                break
            start += len(items)
        return out

    async def resolve(self, media_type: str, tmdb_id: int) -> str | None:
        """Identifiant Plex (ratingKey) d'un titre à partir de son id TMDB."""
        key = ("plex-match", media_type, tmdb_id)
        if (hit := cache.get(key)) is not MISS:
            return hit
        data = await self._req(
            "GET", f"{DISCOVER}/library/metadata/matches", type=1 if media_type == "movie" else 2, guid=f"tmdb://{tmdb_id}"
        )
        items = data.get("MediaContainer", {}).get("Metadata", []) or []
        rk = items[0].get("ratingKey") if items else None
        cache.set(key, rk, 86400 * 7)
        return rk

    async def _key(self, media_type: str, tmdb_id: int) -> str:
        rk = await self.resolve(media_type, tmdb_id)
        if not rk:
            raise ServiceError("plex", "Titre introuvable dans le catalogue Plex", 404)
        return rk

    async def scores(self, media_type: str, tmdb_id: int) -> dict:
        """Notes du public et de la critique fournies par Plex : IMDb, Rotten Tomatoes (critique + public)."""
        key = ("plex-scores", media_type, tmdb_id)
        if (hit := cache.get(key)) is not MISS:
            return hit
        rk = await self.resolve(media_type, tmdb_id)
        out: dict = {}
        if rk:
            data = await self._req("GET", f"{METADATA}/library/metadata/{rk}")
            items = data.get("MediaContainer", {}).get("Metadata", []) or []
            for r in (items[0].get("Rating") or []) if items else []:
                img, val = r.get("image", ""), r.get("value")
                if val is None:
                    continue
                if img.startswith("imdb://"):
                    out["imdb"] = round(float(val), 1)
                elif img.startswith("rottentomatoes://") and r.get("type") == "critic":
                    out["rt_critic"] = round(float(val) * 10)  # pourcentage
                    out["rt_critic_state"] = "certified" if "certified" in img else ("fresh" if "ripe" in img else "rotten")
                elif img.startswith("rottentomatoes://") and r.get("type") == "audience":
                    out["rt_audience"] = round(float(val) * 10)
                    out["rt_audience_state"] = "upright" if "upright" in img else "spilled"
        cache.set(key, out, 86400)
        return out

    async def watch_url(self, media_type: str, tmdb_id: int, season: int | None = None, episode: int | None = None) -> str | None:
        """Page du titre sur watch.plex.tv. Sur iPhone / iPad, c'est le lien que l'app Plex ouvre
        sur la bonne fiche (les liens plex:// mènent à l'accueil) ; on y choisit ensuite son serveur."""
        key = ("plex-slug", media_type, tmdb_id)
        slug = cache.get(key)
        if slug is MISS:
            slug = None
            rk = await self.resolve(media_type, tmdb_id)
            if rk:
                data = await self._req("GET", f"{METADATA}/library/metadata/{rk}")
                items = data.get("MediaContainer", {}).get("Metadata", []) or []
                slug = items[0].get("slug") if items else None
            cache.set(key, slug, 86400 * 7)
        if not slug:
            return None
        if media_type == "movie":
            return f"https://watch.plex.tv/movie/{slug}"
        url = f"https://watch.plex.tv/show/{slug}"
        if season is not None:
            url += f"/season/{season}"
            if episode is not None:
                url += f"/episode/{episode}"
        return url

    # --- Écriture ----------------------------------------------------------------

    async def add_to_watchlist(self, media_type: str, tmdb_id: int) -> None:
        await self._req("PUT", f"{DISCOVER}/actions/addToWatchlist", ratingKey=await self._key(media_type, tmdb_id))

    async def remove_from_watchlist(self, media_type: str, tmdb_id: int) -> None:
        await self._req("PUT", f"{DISCOVER}/actions/removeFromWatchlist", ratingKey=await self._key(media_type, tmdb_id))

    async def mark_watched(self, media_type: str, tmdb_id: int) -> None:
        await self._req("PUT", f"{METADATA}/actions/scrobble", key=await self._key(media_type, tmdb_id), identifier="tv.plex.provider.metadata")

    async def mark_unwatched(self, media_type: str, tmdb_id: int) -> None:
        await self._req("PUT", f"{METADATA}/actions/unscrobble", key=await self._key(media_type, tmdb_id), identifier="tv.plex.provider.metadata")

    async def rate(self, media_type: str, tmdb_id: int, rating10: int) -> None:
        await self._req(
            "PUT", f"{METADATA}/actions/rate", key=await self._key(media_type, tmdb_id), identifier="tv.plex.provider.metadata", rating=rating10
        )

    async def add_many_to_watchlist(self, refs: list[tuple[str, int]], concurrency: int = 4) -> dict:
        sem = asyncio.Semaphore(concurrency)
        ok, failed = 0, []

        async def one(mt: str, tid: int):
            nonlocal ok
            async with sem:
                try:
                    await self.add_to_watchlist(mt, tid)
                    ok += 1
                except ServiceError as e:
                    failed.append({"media_type": mt, "tmdb_id": tid, "error": e.message})

        await asyncio.gather(*(one(mt, tid) for mt, tid in refs))
        return {"added": ok, "failed": failed}
