"""Suivi des séries : saisons et épisodes vus / à voir, disponibilités, lecture d'un épisode précis."""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.services.context import Ctx, get_ctx
from app.services.enrich import plex_keys, stream_providers
from app.services.errors import ServiceError

router = APIRouter(prefix="/episodes", tags=["episodes"])


class EpisodeRef(BaseModel):
    season: int = Field(ge=0, le=1000)
    episode: int = Field(ge=0, le=100_000)


class EpisodesUpdate(BaseModel):
    tmdb_id: int = Field(gt=0)
    episodes: list[EpisodeRef] = Field(max_length=2000)  # une série entière au plus (chaque épisode = un appel au serveur)
    watched: bool = True


async def _plex_leaves(ctx: Ctx, tmdb_id: int) -> dict[tuple[int, int], dict]:
    """Épisodes présents sur le serveur Plex : (saison, épisode) -> {rating_key, viewed, progress, url}."""
    # Vus / progression : uniquement avec le jeton Plex du compte (sinon simple présence sur le serveur)
    client = ctx.plex_own or ctx.plex
    if not client:
        return {}
    own = ctx.plex_own is not None
    show = (await plex_keys(ctx)).get(("tv", tmdb_id))
    if not show:
        return {}
    from app.services.history import _plex_get

    try:
        mc = await _plex_get(ctx, f"/library/metadata/{show['rating_key']}/allLeaves", client=client)
        machine = (await client.identity())["machine_id"]
    except ServiceError:
        return {}
    out = {}
    for e in mc.get("Metadata", []) or []:
        if e.get("parentIndex") is None or e.get("index") is None:
            continue
        progress = round(e["viewOffset"] / e["duration"] * 100) if own and e.get("viewOffset") and e.get("duration") else None
        out[(e["parentIndex"], e["index"])] = {
            "rating_key": e.get("ratingKey"),
            "viewed": own and bool(e.get("viewCount")),
            "progress": progress,
            "url": client.web_url(machine, e.get("ratingKey")),
        }
    return out


async def _trakt_progress(ctx: Ctx, tmdb_id: int) -> set[tuple[int, int]]:
    if not ctx.trakt:
        return set()
    info = await ctx.trakt.lookup("tv", tmdb_id)
    if not info or not info.get("slug"):
        return set()
    data = await ctx.trakt._request("GET", f"/shows/{info['slug']}/progress/watched", params={"specials": "false", "hidden": "false"}) or {}
    return {(s["number"], e["number"]) for s in data.get("seasons", []) for e in s.get("episodes", []) if e.get("completed")}


async def _season_providers(ctx: Ctx, tmdb_id: int, n: int) -> list[dict]:
    try:
        data = await ctx.tmdb._get(f"/tv/{tmdb_id}/season/{n}/watch/providers", ttl=43200, language=None)
    except (ServiceError, AttributeError):
        return []
    entry = data.get("results", {}).get(ctx.country, {})
    from app.services.tmdb_client import normalize_provider

    prov = {k: [normalize_provider(p, k) for p in entry.get(k, [])] for k in ("flatrate", "free", "ads")}
    return stream_providers(prov)


@router.get("/{tmdb_id}")
async def show_episodes(tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    detail = await ctx.tmdb.detail("tv", tmdb_id)
    seasons_meta = [s for s in detail.get("seasons", []) if s["season_number"] > 0] or detail.get("seasons", [])

    async def safe(coro, default):
        try:
            return await coro
        except ServiceError:
            return default

    season_data, providers, leaves, trakt_seen = await asyncio.gather(
        asyncio.gather(*(safe(ctx.tmdb.season(tmdb_id, s["season_number"]), {"episodes": []}) for s in seasons_meta)),
        asyncio.gather(*(_season_providers(ctx, tmdb_id, s["season_number"]) for s in seasons_meta)),
        _plex_leaves(ctx, tmdb_id),
        safe(_trakt_progress(ctx, tmdb_id), set()),
    )

    today = date.today().isoformat()
    seasons, next_ep = [], None
    for meta, sd, prov in zip(seasons_meta, season_data, providers):
        n = meta["season_number"]
        eps = []
        for e in sd.get("episodes", []):
            k = (n, e["episode_number"])
            plex = leaves.get(k)
            watched = k in trakt_seen or bool(plex and plex["viewed"])
            aired = bool(e.get("air_date")) and e["air_date"] <= today
            ep = {
                "number": e["episode_number"], "name": e.get("name"), "air_date": e.get("air_date"), "aired": aired,
                "runtime": e.get("runtime"), "overview": e.get("overview"), "still": e.get("still"),
                "watched": watched, "in_plex": bool(plex), "plex_url": plex["url"] if plex else None,
                "progress": plex["progress"] if plex else None,
            }
            eps.append(ep)
            if next_ep is None and aired and not watched:
                next_ep = {"season": n, "episode": e["episode_number"], "name": e.get("name"), "plex_url": ep["plex_url"], "progress": ep["progress"]}
        seasons.append(
            {
                "season_number": n,
                "name": meta.get("name"),
                "poster": meta.get("poster"),
                "air_date": meta.get("air_date"),
                "episode_count": len(eps) or meta.get("episode_count"),
                "aired_count": sum(1 for e in eps if e["aired"]),
                "watched_count": sum(1 for e in eps if e["watched"]),
                "plex_count": sum(1 for e in eps if e["in_plex"]),
                "providers": prov,
                "episodes": eps,
            }
        )
    total_aired = sum(s["aired_count"] for s in seasons)
    total_watched = sum(s["watched_count"] for s in seasons)
    return {
        "seasons": seasons,
        "next_episode": next_ep,
        "totals": {"aired": total_aired, "watched": total_watched},
        "sources": {"trakt": ctx.trakt is not None, "plex": bool(leaves)},
    }


@router.post("/mark")
async def mark_episodes(body: EpisodesUpdate, ctx: Ctx = Depends(get_ctx)):
    """Marque des épisodes vus / non vus sur Trakt et sur le serveur Plex (épisodes présents)."""
    from collections import defaultdict
    from datetime import datetime, timezone

    services: dict[str, str] = {}
    by_season = defaultdict(list)
    for e in body.episodes:
        by_season[e.season].append(e.episode)

    if ctx.trakt:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        seasons = [
            {"number": s, "episodes": [({"number": n, "watched_at": now} if body.watched else {"number": n}) for n in sorted(eps)]}
            for s, eps in sorted(by_season.items())
        ]
        payload = {"shows": [{"ids": {"tmdb": body.tmdb_id}, "seasons": seasons}]}
        try:
            await ctx.trakt._request("POST", "/sync/history" if body.watched else "/sync/history/remove", json=payload)
            services["trakt"] = "ok"
        except ServiceError as e:
            services["trakt"] = e.message

    leaves = await _plex_leaves(ctx, body.tmdb_id)
    targets = [leaves[(e.season, e.episode)]["rating_key"] for e in body.episodes if (e.season, e.episode) in leaves]
    if targets and ctx.plex_own:
        sem = asyncio.Semaphore(6)

        async def one(rk):
            async with sem:
                await (ctx.plex_own.scrobble(rk) if body.watched else ctx.plex_own.unscrobble(rk))

        try:
            await asyncio.gather(*(one(rk) for rk in targets))
            services["plex"] = "ok"
        except ServiceError as e:
            services["plex"] = e.message
    return {"services": services, "count": len(body.episodes)}
