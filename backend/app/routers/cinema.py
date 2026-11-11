"""Cinémas : recherche de salles et séances à l'affiche (données AlloCiné, France uniquement)."""

import asyncio
from datetime import date as date_cls

from fastapi import APIRouter, Depends, Query

from app.services import allocine_client
from app.services.context import Ctx, get_ctx
from app.services.enrich import plex_keys
from app.services.errors import NotConfigured, ServiceError

router = APIRouter(prefix="/cinema", tags=["cinema"])


@router.get("/countries")
def countries():
    """Pays couverts par la source de séances."""
    return {"results": [{"code": c, "source": name} for c, (_, name) in allocine_client.SITES.items()]}


@router.get("/search")
async def search(q: str = Query(..., min_length=2, max_length=80), country: str = Query("FR", pattern=r"^[A-Za-z]{2}$")):
    return {"results": await allocine_client.search(q, country)}


@router.get("/showtimes")
async def showtimes(date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), ctx: Ctx = Depends(get_ctx)):
    """Films à l'affiche dans tes cinémas pour une date, avec leurs séances par cinéma."""
    cinemas = ctx.settings.cinema_list
    if not cinemas:
        raise NotConfigured("cinema", "Choisis tes cinémas dans le Profil")
    day = date or date_cls.today().isoformat()

    async def one(c: dict):
        try:
            return c, await allocine_client.showtimes(c["id"], day, c.get("country") or "FR"), None
        except ServiceError as e:
            return c, [], e.message

    results = await asyncio.gather(*(one(c) for c in cinemas))

    films: dict = {}
    errors = {}
    for cinema, movies, err in results:
        if err:
            errors[cinema["name"]] = err
        for m in movies:
            if ctx.settings.cinema_films_only and not m.get("is_film", True):
                continue  # opéras, ballets, concerts, spectacles…
            entry = films.setdefault(m["allocine_id"], {"allocine": m, "cinemas": []})
            entry["cinemas"].append({**cinema, "showtimes": m["showtimes"]})

    # Correspondance avec TMDB (affiche, note, fiche SynCiné)
    async def match(entry):
        m = entry["allocine"]
        item = None
        try:
            item = await ctx.tmdb.find_movie(m["original_title"] or m["title"], m["year"])
            if item is None and m["original_title"] and m["original_title"] != m["title"]:
                item = await ctx.tmdb.find_movie(m["title"], m["year"])
        except ServiceError:
            pass
        base = item or {
            "id": None, "media_type": "movie", "title": m["title"], "original_title": m["original_title"],
            "overview": "", "poster": m["poster"], "backdrop": None, "release_date": m["release_date"],
            "year": m["year"], "vote_average": 0, "vote_count": 0, "genre_ids": [], "providers": [],
        }
        if item and m["title"]:
            base["title"] = m["title"]  # titre français d'AlloCiné
        return {
            **base,
            "runtime": m["runtime"],
            "cinemas": entry["cinemas"],
            "showtime_count": sum(len(c["showtimes"]) for c in entry["cinemas"]),
        }

    items = await asyncio.gather(*(match(e) for e in films.values()))
    index = await plex_keys(ctx)
    for i in items:
        i["in_plex"] = i.get("id") is not None and ("movie", i["id"]) in index
    items.sort(key=lambda i: (-i["showtime_count"], i["title"] or ""))
    return {"date": day, "results": items, "cinemas": cinemas, "errors": errors}
