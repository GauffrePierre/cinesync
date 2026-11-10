"""Horaires de diffusion des séries (TVmaze : API publique et gratuite, sans clé ; données sous licence CC BY-SA,
créditées dans l'interface). TMDB ne donne que la date d'un épisode ; TVmaze donne l'heure exacte (UTC), que
l'interface convertit à l'heure locale. Facultatif : toute erreur renvoie None, la date TMDB reste affichée.
Mise en cache (TVmaze limite à 20 requêtes par 10 s) : correspondance des séries 7 jours, prochain épisode 3 h."""

import logging

import httpx

from app.services.cache import MISS, cache
from app.services.http import http

log = logging.getLogger(__name__)
BASE = "https://api.tvmaze.com"


async def _get(path: str, ttl: int, **params) -> dict | None:
    key = ("tvmaze", path, tuple(sorted(params.items())))
    if (hit := cache.get(key)) is not MISS:
        return hit
    try:
        r = await http().get(BASE + path, params=params or None, timeout=10.0, follow_redirects=True)
    except httpx.HTTPError as e:
        log.info("TVmaze injoignable : %s", e.__class__.__name__)
        return None
    data = r.json() if r.status_code == 200 and "json" in r.headers.get("content-type", "") else None
    if r.status_code in (200, 404):  # 404 : série inconnue de TVmaze, mémorisé aussi
        cache.set(key, data, ttl)
    return data


async def show_id(imdb_id: str | None, tvdb_id: int | None) -> int | None:
    """Série TVmaze correspondant aux identifiants IMDb / TheTVDB fournis par TMDB."""
    for param, value in (("imdb", imdb_id), ("thetvdb", tvdb_id)):
        if value:
            show = await _get("/lookup/shows", 7 * 86400, **{param: value})
            if show and show.get("id"):
                return show["id"]
    return None


async def next_episode(imdb_id: str | None, tvdb_id: int | None) -> dict | None:
    """Prochain épisode : {season, episode, name, airstamp (ISO 8601, UTC), channel (chaîne ou plateforme), url}."""
    sid = await show_id(imdb_id, tvdb_id)
    if not sid:
        return None
    show = await _get(f"/shows/{sid}", 3 * 3600, embed="nextepisode")
    ep = ((show or {}).get("_embedded") or {}).get("nextepisode")
    if not ep or not ep.get("airstamp"):
        return None
    channel = (show.get("webChannel") or show.get("network") or {}).get("name")
    return {"season": ep.get("season"), "episode": ep.get("number"), "name": ep.get("name") or "", "airstamp": ep["airstamp"],
            "channel": channel, "url": show.get("url")}
