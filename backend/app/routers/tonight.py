"""« Pour ce soir » : uniquement ce qui se regarde tout de suite (Plex ou tes plateformes), pas encore vu."""

import asyncio
import random
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.models import MediaState
from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich, plex_keys, refs_to_items
from app.services.errors import ServiceError
from app.services.history import _show_key
from app.services.suggestions import suggestions

router = APIRouter(prefix="/tonight", tags=["tonight"])

# Humeurs -> genres TMDB (les ids diffèrent entre films et séries)
MOODS = {
    "rire": {35},
    "frissons": {27, 53, 9648, 80},
    "action": {28, 12, 10759, 10752},
    "evasion": {878, 14, 10765, 16},
    "emotion": {18, 10749},
    "famille": {10751, 16, 10762},
    "comprendre": {99, 36, 10763},
}


async def _runtime(ctx: Ctx, item: dict) -> int | None:
    """Durée (min) : film entier, ou un épisode pour une série. Valeur TMDB mise en cache 24 h."""
    if item.get("duration_min"):
        return item["duration_min"]
    try:
        raw = await ctx.tmdb._get(f"/{item['media_type']}/{item['id']}", ttl=86400)
    except (ServiceError, AttributeError, KeyError):
        return None
    if item["media_type"] == "movie":
        return raw.get("runtime") or None
    return (raw.get("episode_run_time") or [None])[0] or 45  # séries : ~45 min si TMDB ne sait pas


def _available(item: dict, platforms: set[int]) -> bool:
    return bool(item.get("in_plex")) or any(p["id"] in platforms for p in item.get("providers", []))


async def _on_deck(ctx: Ctx, index: dict) -> list[dict]:
    """« En cours » de Plex : épisodes / films commencés, avec la progression."""
    if not ctx.plex_own:  # « en cours » propre au compte
        return []
    from app.services.history import _plex_get

    try:
        mc = await _plex_get(ctx, "/library/onDeck", client=ctx.plex_own)
    except ServiceError:
        return []
    by_key = {i["rating_key"]: i for i in index.values()}
    out = []
    for m in mc.get("Metadata", []) or []:
        if m.get("type") == "episode":
            show = by_key.get(_show_key(m)) or {}
            if not show.get("id"):
                continue
            item = await ctx.tmdb.basic("tv", show["id"]) if not ctx.tmdb.is_mock else None
            if not item:
                continue
            item = {**item, "resume": f"S{m.get('parentIndex', 0):02d}E{m.get('index', 0):02d} · {m.get('title') or ''}"}
        elif m.get("type") == "movie":
            lib = by_key.get(m.get("ratingKey")) or {}
            if not lib.get("id"):
                continue
            item = await ctx.tmdb.basic("movie", lib["id"]) if not ctx.tmdb.is_mock else None
            if not item:
                continue
            item = {**item, "resume": "Reprendre le film"}
        else:
            continue
        if m.get("duration") and m.get("viewOffset"):
            item["progress"] = round(m["viewOffset"] / m["duration"] * 100)
            item["duration_min"] = round((m["duration"] - m["viewOffset"]) / 60000)
        item["in_plex"] = True
        item["plex_url"] = ctx.plex.web_url((await ctx.plex.identity())["machine_id"], m.get("ratingKey"))
        out.append(item)
    return out


@router.get("")
async def tonight(
    media_type: Literal["all", "movie", "tv"] = "all",
    max_runtime: int | None = Query(None, ge=20, le=400),
    mood: str | None = None,
    ctx: Ctx = Depends(get_ctx),
):
    platforms = set(ctx.platforms)
    index = await plex_keys(ctx)
    states = {(r.media_type, r.tmdb_id): r for r in ctx.db.execute(select(MediaState)).scalars()}
    watched = {k for k, r in states.items() if r.watched}

    async def watchlist_items():
        refs = [{"tmdb_id": r.tmdb_id, "media_type": r.media_type, "title": r.title} for r in states.values() if r.in_watchlist and not r.watched]
        items = await refs_to_items(ctx, refs[:150])
        return await enrich(ctx, items)

    async def library_gems():
        lib = [
            i for i in index.values()
            if i.get("id") and not i.get("view_count") and (i["media_type"], i["id"]) not in watched
            and (i["media_type"] == "tv" or (i.get("duration_min") or 0) >= 60)  # pas de courts-métrages
        ]
        lib.sort(key=lambda i: -(i.get("vote_average") or 0))
        top = lib[:80]
        random.shuffle(top)  # des propositions différentes d'un soir à l'autre
        refs = [{"tmdb_id": i["id"], "media_type": i["media_type"], "title": i["title"], "duration_min": i.get("duration_min")} for i in top]
        items = await refs_to_items(ctx, refs)
        for it in items:
            it["in_plex"] = True
            hit = index.get((it["media_type"], it["id"]))
            it["plex_url"] = hit.get("plex_url") if hit else None
        return items

    async def for_you():
        try:
            return await suggestions(ctx, media_type, 40)
        except ServiceError:
            return []

    deck, wl, gems, sugg = await asyncio.gather(_on_deck(ctx, index), watchlist_items(), library_gems(), for_you())

    mood_ids = MOODS.get(mood or "", set())

    async def keep(items: list[dict], check_watched: bool = True) -> list[dict]:
        out = []
        for i in items:
            if media_type != "all" and i["media_type"] != media_type:
                continue
            if check_watched and (i["media_type"], i["id"]) in watched:
                continue
            if not _available(i, platforms):
                continue
            if mood_ids and not (set(i.get("genre_ids") or []) & mood_ids):
                continue
            out.append(i)
        if max_runtime:
            runtimes = await asyncio.gather(*(_runtime(ctx, i) for i in out))
            out = [i | {"runtime": r} for i, r in zip(out, runtimes) if r and r <= max_runtime]
        return out

    sections = {
        "resume": await keep(deck, check_watched=False),
        "watchlist": (await keep(wl))[:20],
        "suggestions": (await keep(sugg))[:20],
        "library": (await keep(gems))[:20],
    }
    # Un titre n'apparaît qu'une fois, dans la section la plus pertinente
    seen = set()
    for name in ("resume", "watchlist", "suggestions", "library"):
        uniq = []
        for i in sections[name]:
            k = (i["media_type"], i["id"])
            if k not in seen:
                seen.add(k)
                uniq.append(i)
        sections[name] = uniq

    pool = sections["watchlist"] + sections["suggestions"] + sections["library"]
    pick = random.choice(pool) if pool else None
    return {"sections": sections, "pick": pick, "moods": list(MOODS)}
