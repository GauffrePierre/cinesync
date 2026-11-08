"""Client TMDB : métadonnées, tendances, à venir, et Watch Providers (données JustWatch)."""

import asyncio
import hashlib
from datetime import date, timedelta

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

IMG_BASE = "https://image.tmdb.org/t/p/"
API_BASE = "https://api.themoviedb.org/3"

# Limite les appels simultanés (enrichissement de listes)
_sem = asyncio.Semaphore(10)


def img(path: str | None, size: str = "w500") -> str | None:
    return f"{IMG_BASE}{size}{path}" if path else None


def normalize(raw: dict, media_type: str | None = None) -> dict | None:
    """Résultat TMDB (liste) -> MediaItem."""
    mt = raw.get("media_type") or media_type
    if mt not in ("movie", "tv"):
        return None
    d = raw.get("release_date") or raw.get("first_air_date") or None
    return {
        "id": raw["id"],
        "media_type": mt,
        "title": raw.get("title") or raw.get("name") or "",
        "original_title": raw.get("original_title") or raw.get("original_name"),
        "overview": raw.get("overview") or "",
        "poster": img(raw.get("poster_path")),
        "backdrop": img(raw.get("backdrop_path"), "w1280"),
        "release_date": d,
        "year": int(d[:4]) if d and len(d) >= 4 else None,
        "vote_average": round(raw.get("vote_average") or 0, 1),
        "vote_count": raw.get("vote_count") or 0,
        "genre_ids": raw.get("genre_ids") or [g["id"] for g in raw.get("genres", [])],
        "providers": [],
        "in_plex": False,
    }


def normalize_list(results: list[dict], media_type: str | None = None) -> list[dict]:
    return [n for r in results if (n := normalize(r, media_type))]


def normalize_provider(p: dict, kind: str) -> dict:
    return {
        "id": p["provider_id"],
        "name": p["provider_name"],
        "logo": img(p.get("logo_path"), "w92"),
        "type": kind,
        "priority": p.get("display_priority", 999),
    }


def _pick_trailer(videos: list[dict], lang: str) -> dict | None:
    yt = [v for v in videos if v.get("site") == "YouTube"]
    for pred in (
        lambda v: v["type"] == "Trailer" and v.get("iso_639_1") == lang,
        lambda v: v["type"] == "Trailer" and v.get("official"),
        lambda v: v["type"] == "Trailer",
        lambda v: v["type"] == "Teaser",
        lambda v: True,
    ):
        for v in yt:
            if pred(v):
                return {"key": v["key"], "name": v.get("name"), "site": "YouTube"}
    return None


def normalize_detail(raw: dict, media_type: str, lang: str = "fr", country: str = "CH") -> dict:
    """Fiche détail TMDB complète -> format « fiche cinéphile »."""
    base = normalize({**raw, "media_type": media_type}) or {}
    is_movie = media_type == "movie"

    # Casting
    if is_movie:
        cast_raw = raw.get("credits", {}).get("cast", [])
        cast = [
            {"id": c["id"], "name": c["name"], "character": c.get("character"), "photo": img(c.get("profile_path"), "w185")}
            for c in cast_raw[:20]
        ]
    else:
        cast_raw = raw.get("aggregate_credits", {}).get("cast") or raw.get("credits", {}).get("cast", [])
        cast = [
            {
                "id": c["id"],
                "name": c["name"],
                "character": (c.get("roles") or [{}])[0].get("character") if c.get("roles") else c.get("character"),
                "photo": img(c.get("profile_path"), "w185"),
                "episodes": c.get("total_episode_count"),
            }
            for c in cast_raw[:20]
        ]

    # Équipe technique
    crew_raw = raw.get("credits", {}).get("crew", [])
    if not is_movie:
        crew_raw = crew_raw + [
            {**c, "job": j.get("job")} for c in raw.get("aggregate_credits", {}).get("crew", []) for j in c.get("jobs", [])
        ]

    def people(jobs: set[str], limit: int = 4) -> list[dict]:
        seen, out = set(), []
        for c in crew_raw:
            if c.get("job") in jobs and c["id"] not in seen:
                seen.add(c["id"])
                out.append({"id": c["id"], "name": c["name"], "job": c.get("job"), "photo": img(c.get("profile_path"), "w185")})
        return out[:limit]

    crew = {
        "directors": people({"Director"}),
        "writers": people({"Screenplay", "Writer", "Novel", "Story", "Author", "Original Story"}),
        "composers": people({"Original Music Composer", "Music", "Composer"}),
        "cinematographers": people({"Director of Photography"}, 2),
        "producers": people({"Producer", "Executive Producer"}, 4),
        "creators": [
            {"id": c["id"], "name": c["name"], "job": "Creator", "photo": img(c.get("profile_path"), "w185")}
            for c in raw.get("created_by", [])
        ],
    }

    # Pays / langues
    countries = [c["name"] for c in raw.get("production_countries", [])] or raw.get("origin_country", [])
    spoken = {l["iso_639_1"]: (l.get("name") or l.get("english_name")) for l in raw.get("spoken_languages", [])}
    orig_lang = raw.get("original_language")

    # Certification (classification d'âge) pour le pays
    certification = None
    if is_movie:
        for r in raw.get("release_dates", {}).get("results", []):
            if r["iso_3166_1"] in (country, "US"):
                certs = [x["certification"] for x in r.get("release_dates", []) if x.get("certification")]
                if certs:
                    certification = certs[0]
                    if r["iso_3166_1"] == country:
                        break
    else:
        for r in raw.get("content_ratings", {}).get("results", []):
            if r["iso_3166_1"] in (country, "US") and r.get("rating"):
                certification = r["rating"]
                if r["iso_3166_1"] == country:
                    break

    videos = raw.get("videos", {}).get("results", [])
    recos = normalize_list(raw.get("recommendations", {}).get("results", []), media_type)
    if not recos:
        recos = normalize_list(raw.get("similar", {}).get("results", []), media_type)

    runtime = raw.get("runtime") if is_movie else ((raw.get("episode_run_time") or [None])[0])

    detail = {
        **base,
        "poster": img(raw.get("poster_path"), "w780"),
        "poster_small": img(raw.get("poster_path"), "w342"),
        "backdrop": img(raw.get("backdrop_path"), "original"),
        "tagline": raw.get("tagline") or None,
        "status": raw.get("status"),
        "homepage": raw.get("homepage") or None,
        "imdb_id": raw.get("imdb_id") or raw.get("external_ids", {}).get("imdb_id"),
        "runtime": runtime,
        "countries": countries,
        "original_language": spoken.get(orig_lang, (orig_lang or "").upper()) if orig_lang else None,
        "spoken_languages": list(spoken.values()),
        "genres": [g["name"] for g in raw.get("genres", [])],
        "keywords": [k["name"] for k in (raw.get("keywords", {}).get("keywords") or raw.get("keywords", {}).get("results") or [])],
        "certification": certification,
        "cast": cast,
        "crew": crew,
        "trailer": _pick_trailer(videos, lang),
        "videos": [
            {"key": v["key"], "name": v.get("name"), "type": v.get("type")} for v in videos if v.get("site") == "YouTube"
        ][:10],
        "recommendations": recos[:20],
        "budget": raw.get("budget") or None,
        "revenue": raw.get("revenue") or None,
        "collection": None,
    }

    if is_movie and raw.get("belongs_to_collection"):
        c = raw["belongs_to_collection"]
        detail["collection"] = {"id": c["id"], "name": c["name"], "poster": img(c.get("poster_path")), "backdrop": img(c.get("backdrop_path"), "w1280"), "parts": []}

    if not is_movie:
        detail.update(
            {
                "seasons": [
                    {
                        "season_number": s["season_number"],
                        "name": s.get("name"),
                        "episode_count": s.get("episode_count"),
                        "air_date": s.get("air_date"),
                        "poster": img(s.get("poster_path"), "w342"),
                        "overview": s.get("overview"),
                        "vote_average": s.get("vote_average"),
                    }
                    for s in raw.get("seasons", [])
                ],
                "number_of_seasons": raw.get("number_of_seasons"),
                "number_of_episodes": raw.get("number_of_episodes"),
                "in_production": raw.get("in_production"),
                "first_air_date": raw.get("first_air_date"),
                "last_air_date": raw.get("last_air_date"),
                "next_episode": raw.get("next_episode_to_air"),
                "last_episode": raw.get("last_episode_to_air"),
                "networks": [{"id": n["id"], "name": n["name"], "logo": img(n.get("logo_path"), "w185")} for n in raw.get("networks", [])],
                "type": raw.get("type"),
            }
        )
    return detail


class TMDBClient:
    is_mock = False

    def __init__(self, api_key: str, language: str = "fr-FR", country: str = "CH"):
        self.api_key = api_key.strip()
        self.language = language or "fr-FR"
        self.lang2 = self.language[:2]
        self.country = country or "CH"
        self._keyhash = hashlib.sha1(self.api_key.encode()).hexdigest()[:8]

    async def _get(self, path: str, ttl: int = 3600, **params) -> dict:
        params.setdefault("language", self.language)  # language=None explicite => paramètre omis
        params = {k: v for k, v in params.items() if v is not None}
        key = ("tmdb", self._keyhash, path, tuple(sorted((k, str(v)) for k, v in params.items())))
        if ttl and (hit := cache.get(key)) is not MISS:
            return hit

        headers = {"Accept": "application/json"}
        if self.api_key.startswith("eyJ"):  # jeton de lecture v4
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            params["api_key"] = self.api_key

        async with _sem:
            try:
                r = await http().get(API_BASE + path, params=params, headers=headers)
            except httpx.HTTPError as e:
                raise ServiceError("tmdb", f"TMDB injoignable : {e.__class__.__name__}") from e
        if r.status_code == 401:
            raise ServiceError("tmdb", "Clé API TMDB invalide", 401)
        if r.status_code == 404:
            raise ServiceError("tmdb", "Titre introuvable sur TMDB", 404)
        if r.status_code == 429:
            raise ServiceError("tmdb", "Trop de requêtes TMDB, réessaie dans un instant", 429)
        if r.status_code >= 400:
            raise ServiceError("tmdb", f"Erreur TMDB ({r.status_code})")
        data = r.json()
        if ttl:
            cache.set(key, data, ttl)
        return data

    # --- Listes -----------------------------------------------------------

    async def trending(self, media_type: str = "all", page: int = 1) -> list[dict]:
        data = await self._get(f"/trending/{media_type}/week", ttl=3600, page=page)
        return normalize_list(data.get("results", []), None if media_type == "all" else media_type)

    async def search_multi(self, query: str, page: int = 1) -> list[dict]:
        data = await self._get("/search/multi", ttl=600, query=query, page=page, include_adult="false")
        return normalize_list(data.get("results", []))

    async def find_movie(self, title: str, year: int | None = None) -> dict | None:
        """Meilleure correspondance TMDB pour un titre (+ année), en tolérant un an d'écart."""
        if not title:
            return None
        for y in ([year, year - 1, year + 1] if year else []) + [None]:
            data = await self._get("/search/movie", ttl=604800, query=title, year=y, include_adult="false")
            res = normalize_list(data.get("results", []), "movie")
            if res:
                return res[0]
        return None

    async def discover(self, media_type: str, page: int = 1, **filters) -> list[dict]:
        data = await self._get(f"/discover/{media_type}", ttl=3600, page=page, **filters)
        return normalize_list(data.get("results", []), media_type)

    # Types de sortie TMDB : 1 avant-première, 2 salles (limitée), 3 salles, 4 numérique, 5 physique, 6 TV
    RELEASE_TYPES = {"cinema": "2|3", "streaming": "4", "all": "2|3|4"}

    async def upcoming(self, media_type: str, page: int = 1, days: int = 120, kind: str = "all") -> list[dict]:
        """Sorties à venir dans le pays.
        Films : kind = "cinema" (salles), "streaming" (numérique) ou "all", avec la date réelle du pays.
        Séries : premières diffusions (classées « streaming »)."""
        today = date.today()
        end = today + timedelta(days=days)
        if media_type == "movie":
            items = await self.discover(
                "movie",
                page=page,
                region=self.country,
                **{
                    # release_date.* filtre sur les dates de sortie du pays pour les types demandés
                    "release_date.gte": today.isoformat(),
                    "release_date.lte": end.isoformat(),
                    "sort_by": "popularity.desc",
                    "with_release_type": self.RELEASE_TYPES[kind],
                },
            )
            await asyncio.gather(*(self._apply_regional_release(i, kind, today, end) for i in items))
            return [i for i in items if i.get("release_date")]
        if kind == "cinema":
            return []
        items = await self.discover(
            "tv",
            page=page,
            **{"first_air_date.gte": today.isoformat(), "first_air_date.lte": end.isoformat(), "sort_by": "popularity.desc"},
        )
        for i in items:
            i["release_kind"] = "streaming"
        return items

    async def release_dates(self, tmdb_id: int) -> dict[str, list[str]]:
        """Dates de sortie du film dans le pays : {"cinema": [...], "streaming": [...]} (AAAA-MM-JJ)."""
        try:
            data = await self._get(f"/movie/{tmdb_id}/release_dates", ttl=86400, language=None)
        except ServiceError:
            return {"cinema": [], "streaming": []}
        out = {"cinema": [], "streaming": []}
        for r in data.get("results", []):
            if r.get("iso_3166_1") != self.country:
                continue
            for rd in r.get("release_dates", []):
                d = (rd.get("release_date") or "")[:10]
                if not d:
                    continue
                if rd.get("type") in (2, 3):
                    out["cinema"].append(d)
                elif rd.get("type") == 4:
                    out["streaming"].append(d)
        return {k: sorted(v) for k, v in out.items()}

    async def _apply_regional_release(self, item: dict, kind: str, start: date, end: date) -> None:
        """Remplace la date mondiale par la date de sortie du pays et indique le type (cinéma / streaming)."""
        dates = await self.release_dates(item["id"])
        lo, hi = start.isoformat(), end.isoformat()
        candidates = []
        for k in (("cinema", "streaming") if kind == "all" else (kind,)):
            candidates += [(d, k) for d in dates[k] if lo <= d <= hi]
        if not candidates:
            item["release_date"] = None
            return
        d, k = min(candidates)
        item["release_date"], item["release_kind"] = d, k
        item["year"] = int(d[:4])

    async def now_playing(self, page: int = 1) -> list[dict]:
        """Films actuellement en salles dans le pays."""
        data = await self._get("/movie/now_playing", ttl=21600, page=page, region=self.country)
        return normalize_list(data.get("results", []), "movie")

    async def on_the_air(self, page: int = 1) -> list[dict]:
        data = await self._get("/tv/on_the_air", ttl=3600, page=page)
        return normalize_list(data.get("results", []), "tv")

    async def recommendations(self, media_type: str, tmdb_id: int, page: int = 1) -> list[dict]:
        data = await self._get(f"/{media_type}/{tmdb_id}/recommendations", ttl=86400, page=page)
        return normalize_list(data.get("results", []), media_type)

    async def similar(self, media_type: str, tmdb_id: int, page: int = 1) -> list[dict]:
        data = await self._get(f"/{media_type}/{tmdb_id}/similar", ttl=86400, page=page)
        return normalize_list(data.get("results", []), media_type)

    # --- Détails ------------------------------------------------------------

    async def detail_raw(self, media_type: str, tmdb_id: int) -> dict:
        if media_type == "movie":
            append = "credits,videos,keywords,recommendations,similar,external_ids,release_dates"
        else:
            append = "credits,aggregate_credits,videos,keywords,recommendations,similar,external_ids,content_ratings"
        return await self._get(
            f"/{media_type}/{tmdb_id}",
            ttl=21600,
            append_to_response=append,
            include_video_language=f"{self.lang2},en,null",
        )

    async def detail(self, media_type: str, tmdb_id: int) -> dict:
        raw = await self.detail_raw(media_type, tmdb_id)
        return normalize_detail(raw, media_type, self.lang2, self.country)

    async def basic(self, media_type: str, tmdb_id: int) -> dict | None:
        """Version légère (pour enrichir des items Trakt/JustWatch avec poster, note…)."""
        try:
            raw = await self._get(f"/{media_type}/{tmdb_id}", ttl=86400)
        except ServiceError as e:
            if e.status == 404:
                return None
            raise
        return normalize(raw, media_type)

    async def season(self, tv_id: int, season_number: int) -> dict:
        raw = await self._get(f"/tv/{tv_id}/season/{season_number}", ttl=21600)
        return {
            "season_number": raw.get("season_number"),
            "name": raw.get("name"),
            "overview": raw.get("overview"),
            "episodes": [
                {
                    "episode_number": e["episode_number"],
                    "name": e.get("name"),
                    "overview": e.get("overview"),
                    "air_date": e.get("air_date"),
                    "runtime": e.get("runtime"),
                    "still": img(e.get("still_path"), "w300"),
                    "vote_average": e.get("vote_average"),
                }
                for e in raw.get("episodes", [])
            ],
        }

    async def collection(self, collection_id: int) -> dict:
        raw = await self._get(f"/collection/{collection_id}", ttl=86400)
        parts = normalize_list(raw.get("parts", []), "movie")
        parts.sort(key=lambda p: p.get("release_date") or "9999")
        return {"id": raw["id"], "name": raw.get("name"), "overview": raw.get("overview"), "parts": parts}

    # --- Watch providers ---------------------------------------------------

    async def providers(self, media_type: str, tmdb_id: int, fresh: bool = False) -> dict:
        """Disponibilités pour le pays configuré : {link, flatrate, free, ads, rent, buy}."""
        data = await self._get(f"/{media_type}/{tmdb_id}/watch/providers", ttl=0 if fresh else 43200, language=None)
        entry = data.get("results", {}).get(self.country, {})
        out = {"link": entry.get("link")}
        for kind in ("flatrate", "free", "ads", "rent", "buy"):
            out[kind] = sorted((normalize_provider(p, kind) for p in entry.get(kind, [])), key=lambda p: p["priority"])
        return out

    async def provider_catalog(self, media_type: str = "movie") -> list[dict]:
        data = await self._get(f"/watch/providers/{media_type}", ttl=604800, watch_region=self.country)
        return [
            {
                "id": p["provider_id"],
                "name": p["provider_name"],
                "logo": img(p.get("logo_path"), "w92"),
                "priority": p.get("display_priorities", {}).get(self.country, p.get("display_priority", 999)),
            }
            for p in data.get("results", [])
        ]

    async def regions(self) -> list[dict]:
        data = await self._get("/watch/providers/regions", ttl=604800)
        return sorted(
            ({"code": r["iso_3166_1"], "name": r.get("native_name") or r.get("english_name")} for r in data.get("results", [])),
            key=lambda r: r["name"],
        )

    async def genres(self, media_type: str) -> dict[int, str]:
        data = await self._get(f"/genre/{media_type}/list", ttl=604800)
        return {g["id"]: g["name"] for g in data.get("genres", [])}

    async def test(self) -> dict:
        data = await self._get("/configuration", ttl=0, language=None)
        return {"images": bool(data.get("images"))}
