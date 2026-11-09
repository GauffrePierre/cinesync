"""Enrichissement des listes : plateformes de streaming + présence dans Plex."""

import asyncio
import logging

from app.services.context import Ctx
from app.services.errors import ServiceError

log = logging.getLogger(__name__)

STREAM_KINDS = ("flatrate", "free", "ads")


def stream_providers(prov: dict) -> list[dict]:
    """Fournisseurs « inclus » (abonnement, gratuit, pub), dédoublonnés."""
    seen, out = set(), []
    for kind in STREAM_KINDS:
        for p in prov.get(kind, []):
            if p["id"] not in seen:
                seen.add(p["id"])
                out.append(p)
    return out


async def plex_keys(ctx: Ctx) -> dict[tuple[str, int], dict]:
    """Titres de la bibliothèque du compte (Plex, sinon Jellyfin / Emby), par (type, id TMDB)."""
    if ctx.media is None:
        return {}
    try:
        return await ctx.media.index()
    except ServiceError as e:
        log.warning("Index de la bibliothèque indisponible : %s", e.message)
        return {}


async def theater_status(ctx: Ctx, tmdb_id: int) -> dict:
    """{"in_theaters": bool, "digital_date": "AAAA-MM-JJ" | None} : sorti en salles récemment, pas encore en numérique."""
    from datetime import date, timedelta

    if ctx.tmdb.is_mock or not hasattr(ctx.tmdb, "release_dates"):
        return {"in_theaters": False, "digital_date": None}
    dates = await ctx.tmdb.release_dates(tmdb_id)
    today = date.today().isoformat()
    recent = (date.today() - timedelta(days=150)).isoformat()
    in_cinema = any(recent <= d <= today for d in dates["cinema"])
    digital_past = any(d <= today for d in dates["streaming"])
    future_digital = next((d for d in dates["streaming"] if d > today), None)
    return {"in_theaters": in_cinema and not digital_past, "digital_date": future_digital}


async def enrich(ctx: Ctx, items: list[dict], providers: bool = True, plex: bool = True) -> list[dict]:
    if not items:
        return items

    async def prov(item: dict) -> None:
        try:
            item["providers"] = stream_providers(await ctx.tmdb.providers(item["media_type"], item["id"]))
        except ServiceError:
            item["providers"] = []
        # Film sans offre de streaming : est-il au cinéma en ce moment ?
        if item["media_type"] == "movie" and not item["providers"]:
            try:
                item.update(await theater_status(ctx, item["id"]))
            except ServiceError:
                pass

    tasks = [prov(i) for i in items if i.get("id")] if providers else []
    index_task = plex_keys(ctx) if plex else None
    results = await asyncio.gather(*tasks, *([index_task] if index_task else []))
    if index_task:
        index = results[-1]
        for i in items:
            hit = index.get((i["media_type"], i.get("id")))
            i["in_plex"] = hit is not None
            if hit:
                i["plex_url"] = hit.get("plex_url")
                i["server"] = hit.get("server", "plex")  # plex | jellyfin | emby
    return items


async def refs_to_items(ctx: Ctx, refs: list[dict], limit: int | None = None) -> list[dict]:
    """Références {tmdb_id, media_type} (Trakt, JustWatch…) -> MediaItems TMDB, en gardant les champs de la ref."""
    refs = refs[:limit] if limit else refs

    async def one(ref: dict) -> dict | None:
        try:
            item = await ctx.tmdb.basic(ref["media_type"], ref["tmdb_id"])
        except ServiceError:
            item = None
        if item is None:
            return {
                "id": ref["tmdb_id"], "media_type": ref["media_type"], "title": ref.get("title") or "",
                "original_title": None, "overview": "", "poster": None, "backdrop": None,
                "release_date": None, "year": ref.get("year"), "vote_average": 0, "vote_count": 0,
                "genre_ids": [], "providers": [], "in_plex": False, **_extra(ref),
            }
        return {**item, **_extra(ref)}

    items = await asyncio.gather(*(one(r) for r in refs))
    return [i for i in items if i]


def _extra(ref: dict) -> dict:
    skip = {"tmdb_id", "media_type", "title", "year"}
    return {k: v for k, v in ref.items() if k not in skip}
