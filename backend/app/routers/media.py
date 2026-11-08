"""Vues agrégées : fiche détail complète (TMDB + dispo + Plex + Trakt + Seerr) et suggestions."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.services.context import Ctx, get_ctx
from app.services.enrich import plex_keys, stream_providers
from app.services.errors import ServiceError
from app.routers.requests import find_open, visible
from app.services.library_sync import state_of
from app.services.suggestions import suggestions

router = APIRouter(prefix="/media", tags=["media"])


def merge_availability(tmdb: dict, jw_offers: list[dict] | None) -> dict:
    """Base TMDB, complétée par les liens directs JustWatch quand ils existent."""
    jw = {(o["id"], o["type"]): o for o in jw_offers or []}

    def group(kinds: tuple[str, ...]) -> list[dict]:
        out, seen = [], set()
        for kind in kinds:
            for p in tmdb.get(kind, []):
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                offer = jw.get((p["id"], kind))
                out.append({**p, "url": offer["url"] if offer else None, "quality": offer.get("quality") if offer else None})
            # Offres JustWatch absentes de TMDB
            for (pid, k), o in jw.items():
                if k == kind and pid not in seen:
                    seen.add(pid)
                    out.append({**o, "priority": 500})
        return out

    return {
        "link": tmdb.get("link"),
        "stream": group(("flatrate", "free", "ads")),
        "rent": group(("rent",)),
        "buy": group(("buy",)),
        "source": "tmdb+justwatch" if jw_offers else "tmdb",
    }


@router.get("/suggestions")
async def get_suggestions(
    media_type: Literal["all", "movie", "tv"] = "all",
    limit: int = Query(20, ge=1, le=60),
    ctx: Ctx = Depends(get_ctx),
):
    items = await suggestions(ctx, media_type, limit)
    return {"results": items, "mock": ctx.tmdb.is_mock}


@router.get("/watchlist-releases")
async def watchlist_releases(ctx: Ctx = Depends(get_ctx)):
    """Sorties récentes de la watchlist (réglage « Découverte » : période en jours, 0 = désactivé)."""
    from app.services.enrich import enrich
    from app.services.suggestions import watchlist_releases as releases

    days = ctx.settings.recent_days or 0
    items = [dict(i) for i in await releases(ctx, days)]
    await enrich(ctx, items)
    return {"results": items, "days": days}


@router.get("/highlights")
async def highlights(ctx: Ctx = Depends(get_ctx)):
    """Diapositives du carrousel de Découvrir : tendance, cinéma, streaming (Plex + plateformes), pour toi."""
    from datetime import date, datetime, timedelta, timezone

    from app.services import allocine_client
    from app.services.enrich import enrich, refs_to_items

    async def safe(coro, default):
        try:
            return await coro
        except ServiceError:
            return default

    # Titres déjà vus ou marqués « pas intéressé » : jamais mis en avant
    from app.models import MediaState

    skip = {(r.media_type, r.tmdb_id) for r in ctx.db.execute(select(MediaState)).scalars() if r.watched or r.disliked}

    def fresh(items):
        return [i for i in items if (i.get("media_type"), i.get("id")) not in skip]

    async def trending():
        all_items = await safe(ctx.tmdb.trending("all"), [])
        items = fresh(all_items)
        if not items:
            return []
        # Le n°1 s'il n'a pas été vu, sinon le premier des tendances qui reste à découvrir
        label = "Tendance n°1 cette semaine" if items[0] is all_items[0] else "Tendance cette semaine"
        return [{"label": label, "kind": "trending", "item": items[0]}]

    async def cinema():
        cinemas = ctx.settings.cinema_list
        if cinemas:
            # Le film le plus programmé aujourd'hui dans tes salles
            counts: dict = {}
            for c in cinemas[:3]:
                for m in await safe(allocine_client.showtimes(c["id"], date.today().isoformat(), c.get("country") or "FR"), []):
                    if ctx.settings.cinema_films_only and not m.get("is_film", True):
                        continue
                    e = counts.setdefault(m["allocine_id"], {"m": m, "n": 0, "cinemas": set()})
                    e["n"] += len(m["showtimes"])
                    e["cinemas"].add(c["name"])
            out = []
            for e in sorted(counts.values(), key=lambda e: -e["n"])[:4]:
                item = await safe(ctx.tmdb.find_movie(e["m"]["original_title"] or e["m"]["title"], e["m"]["year"]), None)
                if item and item.get("backdrop"):
                    item["title"] = e["m"]["title"] or item["title"]
                    out.append({"label": f"Au cinéma · {', '.join(sorted(e['cinemas']))}", "kind": "cinema", "item": item})
                if len(out) == 2:
                    break
            if out:
                return out
        items = [i for i in fresh(await safe(ctx.tmdb.now_playing(), [])) if i.get("backdrop")]
        return [{"label": f"Au cinéma en ce moment ({ctx.country})", "kind": "cinema", "item": i} for i in items[:2]]

    async def streaming():
        out = []
        if ctx.plex:
            lib = await safe(ctx.plex.library(), [])
            recent_cut = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
            recent = sorted(
                (i for i in lib if i.get("id") and (i.get("added_at") or "") >= recent_cut and (i["media_type"], i["id"]) not in skip),
                key=lambda i: i["added_at"], reverse=True,
            )
            for i in recent[:3]:
                item = await safe(ctx.tmdb.basic(i["media_type"], i["id"]), None)
                if item and item.get("backdrop"):
                    out.append({"label": "Nouveau sur ton Plex", "kind": "plex", "item": item})
                    break
        if ctx.justwatch and ctx.platforms:
            new = await safe(ctx.justwatch.new_titles(ctx.platforms, 7), [])
            seen = set()
            refs = [r for r in new if (r["media_type"], r["tmdb_id"]) not in seen and not seen.add((r["media_type"], r["tmdb_id"]))][:15]
            items = await refs_to_items(ctx, refs)
            items = sorted((i for i in items if i.get("backdrop")), key=lambda i: -(i.get("vote_count") or 0))
            for i in items[:2]:
                name = (i.get("provider") or {}).get("name") or "tes plateformes"
                out.append({"label": f"Nouveau sur {name}", "kind": "streaming", "item": i})
        return out

    async def for_you():
        items = await safe(suggestions(ctx, "all", 6, with_enrich=False), [])
        items = [i for i in items if i.get("backdrop")]
        return [{"label": items[0].get("reason") or "Pour toi", "kind": "suggestion", "item": items[0]}] if items else []

    async def recent():
        # Sorties récentes de ta watchlist (réglage « Découverte ») : en tête du carrousel
        from app.services.suggestions import watchlist_releases as releases

        # Seulement si déjà calculé (tâche périodique ou rangée de Découvrir) : le carrousel n'attend pas
        items = [i for i in (await safe(releases(ctx, ctx.settings.recent_days or 0, cached_only=True), None) or []) if i.get("backdrop")]
        return [{"label": "Vient de sortir · dans ta watchlist", "kind": "recent", "item": dict(i)} for i in items[:2]]

    groups = await asyncio.gather(recent(), trending(), cinema(), streaming(), for_you())
    slides, seen = [], set(skip)
    for g in groups:
        for sl in g:
            k = (sl["item"]["media_type"], sl["item"]["id"])
            if k not in seen:
                seen.add(k)
                slides.append(sl)
    await enrich(ctx, [s["item"] for s in slides])
    return {"slides": slides, "mock": ctx.tmdb.is_mock}


@router.get("/{media_type}/{tmdb_id}")
async def full_detail(media_type: Literal["movie", "tv"], tmdb_id: int, ctx: Ctx = Depends(get_ctx)):
    detail = await ctx.tmdb.detail(media_type, tmdb_id)
    errors: dict[str, str] = {}

    async def safe(name: str, coro, default=None):
        try:
            return await coro
        except ServiceError as e:
            errors[name] = e.message
            return default

    async def jw_offers():
        if not ctx.justwatch:
            return None
        offers = await ctx.justwatch.offers(media_type, tmdb_id, detail["title"], detail.get("year"))
        if not offers and detail.get("original_title") and detail["original_title"] != detail["title"]:
            offers = await ctx.justwatch.offers(media_type, tmdb_id, detail["original_title"], detail.get("year"))
        return offers

    async def trakt_public():
        if ctx.trakt_app is None:
            return None
        return await ctx.trakt_app.lookup(media_type, tmdb_id)

    async def scores():
        return await ctx.plex_account.scores(media_type, tmdb_id) if ctx.plex_account else None

    async def seerr():
        if not ctx.seerr:
            return None
        status = await ctx.seerr.media_status(media_type, tmdb_id)
        return status if ctx.is_admin else {k: v for k, v in status.items() if k != "url"}  # adresse : admin seulement

    async def collection():
        c = detail.get("collection")
        if not c:
            return None
        return await ctx.tmdb.collection(c["id"])

    providers, jw, index, t_public, seerr_status, coll, extra_scores = await asyncio.gather(
        safe("tmdb_providers", ctx.tmdb.providers(media_type, tmdb_id), {}),
        safe("justwatch", jw_offers()),
        plex_keys(ctx),
        safe("trakt_public", trakt_public()),
        safe("seerr", seerr()),
        safe("collection", collection()),
        safe("scores", scores()),
    )

    plex_hit = index.get((media_type, tmdb_id))
    # Lien que l'app Plex iOS ouvre sur la bonne fiche (seulement pour un titre présent sur le serveur)
    plex_watch = None
    if plex_hit and ctx.plex_account:
        plex_watch = await safe("plex_watch", ctx.plex_account.watch_url(media_type, tmdb_id))
    theater = {"in_theaters": False, "digital_date": None}
    if media_type == "movie" and not stream_providers(providers or {}):
        from app.services.enrich import theater_status

        theater = await safe("theater", theater_status(ctx, tmdb_id), theater) or theater
    for r in detail.get("recommendations", []):
        r["in_plex"] = (r["media_type"], r["id"]) in index
    if coll and detail.get("collection"):
        for p in coll["parts"]:
            p["in_plex"] = ("movie", p["id"]) in index
        detail["collection"]["parts"] = coll["parts"]
        detail["collection"]["overview"] = coll.get("overview")

    return {
        **detail,
        "availability": merge_availability(providers or {}, jw),
        "country": ctx.country,
        **theater,  # in_theaters, digital_date
        "plex": {
            "configured": ctx.plex is not None,
            "available": plex_hit is not None,
            "url": plex_hit.get("plex_url") if plex_hit else None,
            "watch_url": plex_watch,
            "rating_key": plex_hit.get("rating_key") if plex_hit else None,
        },
        "trakt": {
            "configured": ctx.trakt_app is not None,
            "connected": ctx.trakt is not None,
            **(t_public or {"rating": None, "votes": None, "url": None}),
        },
        # État personnel fusionné : Trakt + Plex + Letterboxd + SynCiné
        "state": state_of(ctx.db, media_type, tmdb_id),
        "sync_targets": [n for n, on in (("trakt", ctx.trakt), ("plex", ctx.plex_account)) if on],
        "seerr": {"configured": ctx.seerr is not None, **(seerr_status or {})},
        # Demande d'ajout en cours pour ce titre (Seerr ou file d'attente)
        "request": visible(ctx, find_open(ctx, media_type, tmdb_id)),
        # Notes public / critique (IMDb, Rotten Tomatoes) via les métadonnées Plex
        "scores": extra_scores or {},
        "errors": errors,
        "mock": ctx.tmdb.is_mock,
    }
