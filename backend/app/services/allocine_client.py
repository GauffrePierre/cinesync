"""Séances de cinéma via les données publiques d'AlloCiné et de ses sites partenaires (non officiel).

Même plateforme (Webedia) dans plusieurs pays : France (AlloCiné), Allemagne (Filmstarts),
Espagne (SensaCine), Turquie (Beyazperde), Mexique (SensaCine MX).
- search(q, pays)         : cinémas d'une ville ou par nom.
- showtimes(id, date)     : films à l'affiche et horaires (VO, VOST…) avec lien de réservation.
Comme JustWatch, c'est une source non officielle : chaque appel est protégé.
"""

import logging

import httpx

from app.services.cache import MISS, cache
from app.services.errors import ServiceError
from app.services.http import http

log = logging.getLogger(__name__)

SITES = {
    "FR": ("https://www.allocine.fr", "AlloCiné"),
    "DE": ("https://www.filmstarts.de", "Filmstarts"),
    "ES": ("https://www.sensacine.com", "SensaCine"),
    "TR": ("https://www.beyazperde.com", "Beyazperde"),
    "MX": ("https://www.sensacine.com.mx", "SensaCine"),
}

VERSIONS = {
    "original": "VO",
    "original_st": "VOST",
    "original_sme": "VOST (SME)",
    "multiple": "VF",
    "multiple_st": "VF ST",
    "multiple_sme": "VF (SME)",
    "local": "VF",
    "dubbed": "VF",
}


def site_of(country: str) -> str:
    return SITES.get((country or "FR").upper(), SITES["FR"])[0]


async def _get(path: str, ttl: int, country: str = "FR") -> dict:
    base = site_of(country)
    key = ("allocine", base, path)
    if ttl and (hit := cache.get(key)) is not MISS:
        return hit
    try:
        r = await http().get(f"{base}/_{path}", headers={"Accept": "application/json"}, timeout=20.0)
    except httpx.HTTPError as e:
        raise ServiceError("cinema", f"AlloCiné injoignable : {e.__class__.__name__}") from e
    if r.status_code == 404:
        return {}
    if r.status_code >= 400:
        raise ServiceError("cinema", f"AlloCiné indisponible ({r.status_code})")
    try:
        data = r.json()
    except ValueError as e:
        raise ServiceError("cinema", "Réponse AlloCiné inattendue — le site a peut-être changé") from e
    if ttl:
        cache.set(key, data, ttl)
    return data


async def search(query: str, country: str = "FR") -> list[dict]:
    q = query.strip().lower().replace(" ", "-")
    if len(q) < 2:
        return []
    data = await _get(f"/localization_city/{q}", ttl=86400, country=country)
    out = []
    for t in data.get("values", {}).get("theaters", []):
        n = t.get("node", {})
        loc = n.get("location") or {}
        if n.get("internalId"):
            out.append({"id": n["internalId"], "name": n.get("name"), "city": loc.get("city"), "zip": loc.get("zip"), "country": country.upper()})
    return out


def _movie(m: dict) -> dict:
    # FEATURE_FILM = vrai film ; SPECIAL_EVENT = opéra, ballet, concert, spectacle, retransmission…
    rel = (m.get("releases") or [{}])[0].get("releaseDate") or {}
    date = rel.get("date") if isinstance(rel, dict) else None
    poster = (m.get("poster") or {}).get("url")
    return {
        "allocine_id": m.get("internalId"),
        "title": m.get("title"),
        "original_title": m.get("originalTitle"),
        "release_date": date,
        "year": int(date[:4]) if date else None,
        "poster": poster,
        "runtime": m.get("runtime"),
        "is_film": m.get("type", "FEATURE_FILM") == "FEATURE_FILM",
        "event_genres": [g.get("tag") for g in (m.get("genres") or []) if g.get("tag") in ("OPERA", "BALLET", "CONCERT", "SHOW", "THEATER")],
    }


def _showtime(s: dict, group: str, country: str = "FR") -> dict:
    ticketing = (s.get("data") or {}).get("ticketing") or []
    url = next((u for t in ticketing for u in (t.get("urls") or []) if u), None)
    fmt = [p.get("name") for p in (s.get("projection") or []) if isinstance(p, dict) and p.get("name")]
    return {
        "starts_at": s.get("startsAt"),
        # « multiple » = version doublée dans la langue du pays (VF en France)
        "version": VERSIONS.get(group, group.upper()) if country == "FR" else VERSIONS.get(group, group.upper()).replace("VF", "Doublée"),
        "format": ", ".join(fmt) if fmt else None,
        "booking_url": url,
    }


async def showtimes(theater_id: str, day: str, country: str = "FR") -> list[dict]:
    """Films et séances d'un cinéma pour une date (AAAA-MM-JJ)."""
    out, page, total_pages = [], 1, 1
    while page <= total_pages and page <= 5:
        path = f"/showtimes/theater-{theater_id}/d-{day}/" + (f"p-{page}/" if page > 1 else "")
        data = await _get(path, ttl=1800, country=country)
        total_pages = (data.get("pagination") or {}).get("totalPages") or 1
        for res in data.get("results", []) or []:
            groups = res.get("showtimes") or {}
            times = [_showtime(s, g, country) for g, lst in groups.items() for s in (lst or [])]
            times.sort(key=lambda t: t["starts_at"] or "")
            if times:
                out.append({**_movie(res.get("movie") or {}), "showtimes": times})
        page += 1
    return out
