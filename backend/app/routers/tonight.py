"""« Pour ce soir » : uniquement ce qui se regarde tout de suite (Plex ou tes plateformes).
Par défaut ce qui n'a pas encore été vu ; filtre « vus » : des titres déjà vus, à revoir."""

import asyncio
import random
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.models import MediaState
from app.services.clock import utcnow
from app.services.context import Ctx, get_ctx
from app.services.enrich import enrich, plex_keys, refs_to_items
from app.services.errors import ServiceError
from app.services.history import _show_key
from app.services.sorting import sort_items
from app.services.suggestions import suggestions

router = APIRouter(prefix="/tonight", tags=["tonight"])

# Envies -> genres TMDB (les ids diffèrent entre films et séries)
MOODS = {
    "rire": {35},
    "frissons": {53, 9648},
    "peur": {27},
    "enquete": {80, 9648},
    "action": {28, 10759},
    "aventure": {12, 10759},
    "evasion": {878, 14, 10765},
    "animation": {16},
    "emotion": {18},
    "romance": {10749},
    "famille": {10751, 10762},
    "histoire": {36, 10752, 10768},
    "western": {37},
    "musique": {10402},
    "comprendre": {99, 10763},
}


def _recent(i: dict) -> bool:
    d = i.get("release_date") or ""
    return bool(d) and d >= (date.today() - timedelta(days=365)).isoformat()


# Envies d'après la classification (âge minimum conseillé) : (âge max, genres familiaux requis ou non)
AGE_MOODS = {
    "petits": (6, True),   # 3-6 ans : animation, famille, jeunesse
    "enfants": (10, True),  # 7-10 ans
    "ados": (14, False),   # 11-14 ans
}
FAMILY_GENRES = {16, 10751, 10762, 12, 14, 35}  # animation, famille, jeunesse, aventure, fantastique, comédie

# Envies de saison : mots-clés TMDB (Noël, Halloween)
KEYWORD_MOODS = {"noel": {207317}, "halloween": {3335}}

# Envies de cinéphile, sans genre : d'après la note, la notoriété ou l'âge du titre
SPECIAL_MOODS = {
    "pepites": lambda i: (i.get("vote_average") or 0) >= 7.2 and 50 <= (i.get("vote_count") or 0) < 1500,  # méconnus mais très bien notés
    "classiques": lambda i: (i.get("year") or 9999) < 1990 and (i.get("vote_average") or 0) >= 7.0,
    "recents": _recent,  # sortis ces 12 derniers mois
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


async def _resume_items(ctx: Ctx, entries: list[tuple[str, int | None, dict]]) -> list[dict]:
    """Fiches TMDB des titres à reprendre, demandées en parallèle : (film|tv, id TMDB, champs à ajouter)."""
    if ctx.tmdb.is_mock:
        return []
    found = await asyncio.gather(*(ctx.tmdb.basic(mt, tmdb) for mt, tmdb, _ in entries if tmdb), return_exceptions=True)
    extras = [extra for _, tmdb, extra in entries if tmdb]
    return [{**item, **extra} for item, extra in zip(found, extras) if item and not isinstance(item, BaseException)]


async def _jellyfin_deck(ctx: Ctx, index: dict) -> list[dict]:
    """« Reprendre » de Jellyfin / Emby : titres commencés (progression), puis épisode suivant des séries en cours."""
    j = ctx.jellyfin
    try:
        started = await j.in_progress()
    except ServiceError:
        return []
    by_key = {i["rating_key"]: i for i in index.values()}
    entries = []
    for p in started:
        if p["kind"] == "episode":
            tmdb, media_type = (by_key.get(p["series_id"]) or {}).get("id"), "tv"
            label = f"S{p['season'] or 0:02d}E{p['episode'] or 0:02d} · {p['title']}"
        else:
            tmdb, media_type, label = p["tmdb"] or (by_key.get(p["item_id"]) or {}).get("id"), "movie", "Reprendre le film"
        extra = {"resume": label, "in_plex": True, "server": j.kind, "plex_url": j.web_url(p["item_id"])}
        if p.get("progress") is not None:
            extra["progress"], extra["duration_min"] = p["progress"], p["remaining_min"]
        entries.append((media_type, tmdb, extra))
    return await _resume_items(ctx, entries)


async def _on_deck(ctx: Ctx, index: dict) -> list[dict]:
    """« En cours » de Plex : épisodes / films commencés, avec la progression (sinon ceux de Jellyfin / Emby)."""
    if not ctx.plex_own:  # « en cours » propre au compte
        j = getattr(ctx, "jellyfin", None)
        return await _jellyfin_deck(ctx, index) if j and j.user_id and not ctx.plex else []
    from app.services.history import _plex_get

    try:
        mc = await _plex_get(ctx, "/library/onDeck", client=ctx.plex_own)
        machine_id = (await ctx.plex.identity())["machine_id"]
    except ServiceError:
        return []
    by_key = {i["rating_key"]: i for i in index.values()}
    entries = []
    for m in mc.get("Metadata", []) or []:
        if m.get("type") == "episode":
            media_type, tmdb = "tv", (by_key.get(_show_key(m)) or {}).get("id")
            label = f"S{m.get('parentIndex', 0):02d}E{m.get('index', 0):02d} · {m.get('title') or ''}"
        elif m.get("type") == "movie":
            media_type, tmdb, label = "movie", (by_key.get(m.get("ratingKey")) or {}).get("id"), "Reprendre le film"
        else:
            continue
        extra = {"resume": label, "in_plex": True, "plex_url": ctx.plex.web_url(machine_id, m.get("ratingKey"))}
        if m.get("duration") and m.get("viewOffset"):
            extra["progress"] = round(m["viewOffset"] / m["duration"] * 100)
            extra["duration_min"] = round((m["duration"] - m["viewOffset"]) / 60000)
        entries.append((media_type, tmdb, extra))
    return await _resume_items(ctx, entries)


@router.get("")
async def tonight(
    media_type: Literal["all", "movie", "tv"] = "all",
    max_runtime: int | None = Query(None, ge=20, le=400),
    mood: str | None = Query(None, max_length=40),
    sort: Literal["relevance", "release", "title", "year", "rating", "critics", "audience", "added"] = "relevance",
    seen: Literal["unseen", "seen", "all"] = "unseen",
    tz_offset_min: int = Query(0, ge=-840, le=840),  # fuseau de l'appareil (jour de la semaine local)
    with_user: int | None = None,  # (ancien paramètre) soirée « à deux » avec un membre
    with_users: str | None = Query(None, max_length=200),  # soirée avec des membres qui partagent leurs goûts (ids, virgules)
    kids: bool = False,  # avec les enfants du foyer (Préférences) : âge du plus jeune et titres familiaux
    ctx: Ctx = Depends(get_ctx),
):
    from fastapi import HTTPException

    from app.services import family
    from app.services.habits import evening_habit, nearly_finished

    wanted = {int(x) for x in (with_users or "").split(",") if x.strip().isdigit()} | ({with_user} if with_user is not None else set())
    group = [family.partner(ctx, uid) for uid in sorted(wanted)]
    if any(u is None for u in group):
        raise HTTPException(404, "Ce membre ne partage pas ses goûts (ou toi non plus)")
    duo = bool(group)  # soirée à plusieurs
    # Âge et genres : envie « Petits / Enfants / Ados », ou enfants du foyer — la règle la plus stricte
    rules = [AGE_MOODS[mood]] if mood in AGE_MOODS else []
    rules += [AGE_MOODS[k] for k in ctx.settings.kids] if kids else []
    age_rule = (min(r[0] for r in rules), any(r[1] for r in rules)) if rules else None
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

    async def rewatch_items():
        # Déjà vus, à revoir : coups de cœur et mieux notés d'abord
        if seen == "unseen":
            return []
        rows = sorted((r for r in states.values() if r.watched and not r.disliked), key=lambda r: (not r.liked, -(r.rating or 0)))
        refs = [{"tmdb_id": r.tmdb_id, "media_type": r.media_type, "title": r.title} for r in rows[:120]]
        return await enrich(ctx, await refs_to_items(ctx, refs))

    async def finish_items():
        """Séries commencées presque finies (peu d'épisodes sortis restant à voir)."""
        if seen != "unseen" or ctx.tmdb.is_mock:
            return []
        shows = await nearly_finished(ctx)
        remaining = {s["tmdb_id"]: s["remaining"] for s in shows}
        items = await refs_to_items(ctx, [{"tmdb_id": s["tmdb_id"], "media_type": "tv"} for s in shows])
        return [i | {"remaining": remaining.get(i["id"])} for i in await enrich(ctx, items)]

    async def for_you():
        try:
            return await suggestions(ctx, media_type, 40, discovery=False)  # ce soir : ce qui est disponible d'abord
        except ServiceError:
            return []

    async def themed():
        """Envies de saison ou pour enfants : des titres de ce thème disponibles sur tes plateformes (TMDB)."""
        if (mood not in KEYWORD_MOODS and not age_rule) or not platforms or ctx.tmdb.is_mock:
            return []
        filters = {"watch_region": ctx.country, "with_watch_providers": "|".join(str(p) for p in platforms),
                   "with_watch_monetization_types": "flatrate|free|ads", "sort_by": "popularity.desc"}
        if mood in KEYWORD_MOODS:
            filters["with_keywords"] = "|".join(str(k) for k in KEYWORD_MOODS[mood])
        else:
            filters["with_genres"] = "10751|16|10762"
        types = [media_type] if media_type != "all" else ["movie", "tv"]
        pages = await asyncio.gather(*(ctx.tmdb.discover(t, **filters) for t in types), return_exceptions=True)
        items = [i for p in pages if isinstance(p, list) for i in p][:40]
        return await enrich(ctx, items)

    unseen = seen != "seen"
    if duo:  # à plusieurs : vos watchlists en commun, puis des titres pour vous tous
        members = [(u.id, u.name) for u in group]
        both, pair, theme = await asyncio.gather(family.common_watchlist(ctx, [u.id for u in group]), family.together(ctx, members, media_type),
                                                 themed() if unseen else asyncio.sleep(0, []))
        # Titres du thème (enfants, Noël…) : ni vus ni écartés par les autres membres
        unwanted = set().union(*(family.unwanted(ctx, u.id) for u in group))
        theme = [i for i in theme if (i["media_type"], i["id"]) not in unwanted]
        deck = finish = wl = gems = sugg = again = []
    else:
        both = pair = []
    deck, finish, wl, gems, sugg, again, theme = (deck, finish, wl, gems, sugg, again, theme) if duo else await asyncio.gather(
        _on_deck(ctx, index),
        finish_items(),
        watchlist_items() if unseen else asyncio.sleep(0, []),
        library_gems() if unseen else asyncio.sleep(0, []),
        for_you() if unseen else asyncio.sleep(0, []),
        rewatch_items(),
        themed() if unseen else asyncio.sleep(0, []),
    )
    sugg = theme + sugg  # titres du thème d'abord dans les suggestions

    mood_ids = MOODS.get(mood or "", set())
    special = SPECIAL_MOODS.get(mood or "")

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
            if special and not special(i):
                continue
            out.append(i)
        if age_rule and out and hasattr(ctx.tmdb, "min_age"):
            max_age, family_only = age_rule
            if family_only:
                out = [i for i in out if set(i.get("genre_ids") or []) & FAMILY_GENRES]
            out = out[:80]
            ages = await asyncio.gather(*(ctx.tmdb.min_age(i["media_type"], i["id"]) for i in out))
            out = [i for i, a in zip(out, ages) if a is not None and a <= max_age]  # classification inconnue : écarté
        if mood in KEYWORD_MOODS and out and hasattr(ctx.tmdb, "keyword_ids"):
            out = out[:80]
            kws = await asyncio.gather(*(ctx.tmdb.keyword_ids(i["media_type"], i["id"]) for i in out))
            out = [i for i, k in zip(out, kws) if k & KEYWORD_MOODS[mood]]
            if mood == "noel":  # Noël en famille : pas de films d'horreur (même situés à Noël)
                out = [i for i in out if 27 not in (i.get("genre_ids") or [])]
        if max_runtime:
            runtimes = await asyncio.gather(*(_runtime(ctx, i) for i in out))
            out = [i | {"runtime": r} for i, r in zip(out, runtimes) if r and r <= max_runtime]
        return out

    sections = {
        "together_watchlist": await keep(both),
        "together": await keep(pair),
        "resume": await keep(deck, check_watched=False),
        "finish": await keep(finish, check_watched=False),
        "watchlist": await keep(wl),
        "suggestions": await keep(sugg),
        "library": await keep(gems),
        "rewatch": await keep(again, check_watched=False),
    }
    if sort != "relevance":
        # Infos de tri : notes critique / public et date d'ajout connues pour les titres suivis (watchlist)
        for name in ("watchlist", "suggestions", "library", "rewatch"):
            for i in sections[name]:
                st = states.get((i["media_type"], i["id"]))
                if st:
                    i.setdefault("critic_score", st.critic_score)
                    i.setdefault("audience_score", st.audience_score)
                    i["added"] = st.listed_at
            sections[name] = sort_items(sections[name], sort)
    # Habitude de ce jour de la semaine (plutôt des épisodes, ou plutôt des films) : ce type passe devant
    weekday = (utcnow() + timedelta(minutes=tz_offset_min)).weekday()
    habit = evening_habit(ctx, weekday, tz_offset_min) if media_type == "all" else None
    if habit and sort == "relevance":
        for name in ("watchlist", "suggestions", "library"):
            order = {id(i): n - (4 if i["media_type"] == habit["prefer"] else 0) for n, i in enumerate(sections[name])}
            sections[name].sort(key=lambda i: order[id(i)])
    for name in ("together_watchlist", "together", "finish", "watchlist", "suggestions", "library", "rewatch"):
        sections[name] = sections[name][:20]
    # Un titre n'apparaît qu'une fois, dans la section la plus pertinente
    placed = set()
    for name in ("together_watchlist", "together", "resume", "finish", "watchlist", "suggestions", "library", "rewatch"):
        uniq = []
        for i in sections[name]:
            k = (i["media_type"], i["id"])
            if k not in placed:
                placed.add(k)
                uniq.append(i)
        sections[name] = uniq

    pool = (sections["together_watchlist"] + sections["together"] + sections["finish"] + sections["watchlist"] + sections["suggestions"]
            + sections["library"] + sections["rewatch"])
    preferred = [i for i in pool if habit and i["media_type"] == habit["prefer"]]
    pick = random.choice(preferred if preferred and random.random() < 0.7 else pool) if pool else None
    return {"sections": sections, "pick": pick, "habit": habit and {**habit, "weekday": weekday}, "together_with": ", ".join(u.name for u in group) or None, "kids": bool(age_rule) and kids, "moods": list(MOODS) + list(SPECIAL_MOODS) + list(AGE_MOODS) + list(KEYWORD_MOODS)}
