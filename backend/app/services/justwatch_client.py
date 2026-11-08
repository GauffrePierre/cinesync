"""Client JustWatch — API GraphQL INTERNE, non officielle.

Apporte ce que TMDB ne donne pas : liens directs vers chaque plateforme et
« nouveautés par plateforme ». Peut casser sans prévenir : chaque appel est
protégé et l'application retombe alors sur les données TMDB.
Les packageId JustWatch correspondent aux ids fournisseurs TMDB (Netflix = 8…).
"""

import asyncio
import logging
from datetime import date, timedelta

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

log = logging.getLogger(__name__)

GQL_URL = "https://apis.justwatch.com/graphql"
ICON_BASE = "https://images.justwatch.com"

_SEARCH = """
query Search($country: Country!, $language: Language!, $first: Int!, $filter: TitleFilter) {
  popularTitles(country: $country, first: $first, filter: $filter) {
    edges { node {
      id objectType
      content(country: $country, language: $language) {
        title originalReleaseYear fullPath
        externalIds { imdbId tmdbId }
      }
      offers(country: $country, platform: WEB) {
        monetizationType presentationType standardWebURL
        package { packageId clearName technicalName shortName icon }
      }
    } }
  }
}"""

_PACKAGES = """
query Packages($country: Country!) {
  packages(country: $country, platform: WEB) { packageId clearName shortName technicalName icon }
}"""

_NEW = """
query NewTitles($country: Country!, $date: Date!, $language: Language!, $first: Int!, $filter: TitleFilter, $pageType: NewPageType!) {
  newTitles(country: $country, date: $date, first: $first, filter: $filter, pageType: $pageType, priceDrops: false) {
    edges {
      newOffer(platform: WEB) { monetizationType standardWebURL package { packageId clearName icon } }
      node {
        id objectType
        ... on MovieOrShowOrSeason { content(country: $country, language: $language) { title originalReleaseYear externalIds { tmdbId } } }
        ... on Season { show { content(country: $country, language: $language) { title externalIds { tmdbId } } } }
      }
    }
  }
}"""

_CHARTS = """
query Charts($country: Country!, $language: Language!, $first: Int!, $filter: StreamingChartsFilter) {
  streamingCharts(country: $country, first: $first, filter: $filter) {
    edges {
      streamingChartInfo { rank trend trendDifference daysInTop10 topRank }
      node { objectType content(country: $country, language: $language) { title externalIds { tmdbId } } }
    }
  }
}"""

_QUALITY = {"_4K": 4, "UHD": 4, "HD": 3, "SD": 2}
_MONETIZATION = {"FLATRATE": "flatrate", "FREE": "free", "ADS": "ads", "RENT": "rent", "BUY": "buy"}


def icon_url(icon: str | None) -> str | None:
    if not icon:
        return None
    return ICON_BASE + icon.replace("{profile}", "s100").replace("{format}", "webp")


class JustWatchClient:
    def __init__(self, country: str = "CH", language: str = "fr-FR"):
        self.country = country.upper()
        self.lang = (language or "fr")[:2]

    async def _gql(self, query: str, variables: dict, ttl: int) -> dict:
        key = ("justwatch", query[:30], tuple(sorted((k, str(v)) for k, v in variables.items())))
        if ttl and (hit := cache.get(key)) is not MISS:
            return hit
        try:
            r = await http().post(GQL_URL, json={"query": query, "variables": variables}, headers={"Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise ServiceError("justwatch", f"JustWatch injoignable : {e.__class__.__name__}") from e
        if r.status_code >= 400:
            raise ServiceError("justwatch", f"API JustWatch indisponible ({r.status_code})")
        body = r.json()
        if body.get("errors"):
            log.warning("JustWatch GraphQL errors: %s", body["errors"][:1])
            raise ServiceError("justwatch", "L'API JustWatch a changé — repli sur TMDB")
        data = body.get("data") or {}
        if ttl:
            cache.set(key, data, ttl)
        return data

    async def offers(self, media_type: str, tmdb_id: int, title: str, year: int | None = None) -> list[dict]:
        """Offres avec lien direct pour un titre. Correspondance par id TMDB, sinon titre + année."""
        variables = {
            "country": self.country,
            "language": self.lang,
            "first": 5,
            "filter": {"searchQuery": title, "objectTypes": ["MOVIE" if media_type == "movie" else "SHOW"]},
        }
        data = await self._gql(_SEARCH, variables, ttl=43200)
        nodes = [e["node"] for e in data.get("popularTitles", {}).get("edges", [])]
        match = next((n for n in nodes if str((n.get("content") or {}).get("externalIds", {}).get("tmdbId")) == str(tmdb_id)), None)
        if match is None and year:
            match = next((n for n in nodes if (n.get("content") or {}).get("originalReleaseYear") == year), None)
        if match is None:
            return []

        best: dict[tuple[int, str], dict] = {}
        for o in match.get("offers") or []:
            pkg = o.get("package") or {}
            kind = _MONETIZATION.get(o.get("monetizationType"))
            if not kind or not pkg.get("packageId"):
                continue
            k = (pkg["packageId"], kind)
            q = _QUALITY.get(o.get("presentationType"), 1)
            if k not in best or q > best[k]["_q"]:
                best[k] = {
                    "id": pkg["packageId"],
                    "name": pkg.get("clearName"),
                    "logo": icon_url(pkg.get("icon")),
                    "url": o.get("standardWebURL"),
                    "type": kind,
                    "quality": o.get("presentationType"),
                    "_q": q,
                }
        out = list(best.values())
        for o in out:
            o.pop("_q", None)
        return out

    async def packages(self) -> dict[int, dict]:
        data = await self._gql(_PACKAGES, {"country": self.country}, ttl=604800)
        return {p["packageId"]: p for p in data.get("packages", [])}

    async def new_titles(self, provider_ids: list[int], days: int = 7, per_day: int = 40) -> list[dict]:
        """Nouveautés des N derniers jours sur les plateformes données."""
        pkgs = await self.packages()
        short_names = [pkgs[p]["shortName"] for p in provider_ids if p in pkgs]
        if not short_names:
            return []

        async def one_day(d: date) -> list[dict]:
            variables = {
                "country": self.country,
                "language": self.lang,
                "first": per_day,
                "date": d.isoformat(),
                "pageType": "NEW",
                "filter": {"packages": short_names},
            }
            try:
                data = await self._gql(_NEW, variables, ttl=21600)
            except ServiceError:
                return []
            out = []
            for e in data.get("newTitles", {}).get("edges", []):
                node, offer = e.get("node") or {}, e.get("newOffer") or {}
                pkg = offer.get("package") or {}
                ot = node.get("objectType")
                season = None
                if ot == "SHOW_SEASON":
                    show = (node.get("show") or {}).get("content") or {}
                    tmdb, title, mt = show.get("externalIds", {}).get("tmdbId"), show.get("title"), "tv"
                    season = (node.get("content") or {}).get("title")
                else:
                    c = node.get("content") or {}
                    tmdb, title, mt = c.get("externalIds", {}).get("tmdbId"), c.get("title"), ("movie" if ot == "MOVIE" else "tv")
                if not tmdb:
                    continue
                try:
                    tmdb_id = int(str(tmdb).split(":")[0])
                except ValueError:
                    continue
                out.append(
                    {
                        "tmdb_id": tmdb_id,
                        "media_type": mt,
                        "title": title,
                        "season": season,
                        "date": d.isoformat(),
                        "provider": {"id": pkg.get("packageId"), "name": pkg.get("clearName"), "logo": icon_url(pkg.get("icon"))},
                        "url": offer.get("standardWebURL"),
                    }
                )
            return out

        today = date.today()
        days_lists = await asyncio.gather(*(one_day(today - timedelta(days=i)) for i in range(days)))
        return [item for day in days_lists for item in day]

    async def charts(self, media_type: str, first: int = 10) -> list[dict]:
        """Classement du jour JustWatch (popularité quotidienne) pour films ou séries."""
        variables = {
            "country": self.country,
            "language": self.lang,
            "first": first,
            "filter": {"category": "DAILY_POPULARITY_SAME_CONTENT_TYPE", "objectType": "MOVIE" if media_type == "movie" else "SHOW"},
        }
        data = await self._gql(_CHARTS, variables, ttl=3600)
        out = []
        for e in data.get("streamingCharts", {}).get("edges", []):
            info = e.get("streamingChartInfo") or {}
            c = (e.get("node") or {}).get("content") or {}
            tmdb = (c.get("externalIds") or {}).get("tmdbId")
            if not tmdb:
                continue
            out.append(
                {
                    "tmdb_id": int(str(tmdb).split(":")[0]),
                    "media_type": media_type,
                    "title": c.get("title"),
                    "rank": info.get("rank"),
                    "trend": info.get("trend"),  # UP | DOWN | STABLE
                    "trend_diff": info.get("trendDifference"),
                    "days_in_top10": info.get("daysInTop10"),
                }
            )
        return out

    async def test(self) -> dict:
        pkgs = await self.packages()
        return {"packages": len(pkgs)}
