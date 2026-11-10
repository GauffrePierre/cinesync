"""Suggestions en famille, entre comptes qui ont choisi de partager leurs goûts (Profil → Préférences → Partage) :
« La famille a aimé » (Découvrir) et « À deux » (Pour ce soir). Seuls les comptes qui partagent se voient entre
eux, et seulement à travers ces suggestions : rien d'autre de leur compte n'est lu ni renvoyé."""

import asyncio
import math

from sqlalchemy import select

from app.config import config
from app.models import MediaState, User, UserSettings
from app.services.context import Ctx
from app.services.enrich import enrich, refs_to_items
from app.services.suggestions import _of, _quality, _reason, _safe, _variety, excluded_keys, seeds, signals


def partners(ctx: Ctx) -> list[User]:
    """Comptes actifs qui partagent leurs goûts — vide si le compte courant ne partage pas les siens."""
    if config.cinesync_mode != "server" or not ctx.settings.own.share_taste:
        return []
    sharing = set(ctx.db.execute(select(UserSettings.id).where(UserSettings.share_taste.is_(True))).scalars())
    return [u for u in ctx.db.query(User).filter(User.active.is_(True), User.id != ctx.user.id).order_by(User.id) if u.id in sharing]


def partner(ctx: Ctx, user_id: int) -> User | None:
    return next((u for u in partners(ctx) if u.id == user_id), None)


def _loved(ctx: Ctx, uid: int | None, media_types: list[str]) -> dict[tuple[str, int], dict]:
    """Titres vraiment aimés (coup de cœur, note ≥ 8, « J'aime » du swipe ou « plus comme ça ») d'un compte."""
    pos, _ = signals(ctx, media_types, uid)
    return {(s["media_type"], s["tmdb_id"]): s for s in pos if s["weight"] >= 1.2}


def unwanted(ctx: Ctx, uid: int) -> set[tuple[str, int]]:
    """Ce qu'un autre compte a déjà vu ou rejeté (à ne pas proposer « à deux »)."""
    return {(r.media_type, r.tmdb_id) for r in ctx.db.execute(_of(MediaState, uid)).scalars() if r.watched or r.disliked}


async def family_loved(ctx: Ctx, media_type: str = "all", limit: int = 20, only: list[int] | None = None) -> list[dict]:
    """Titres aimés par les membres qui partagent (ou seulement ceux choisis), pondérés par la proximité de goûts,
    pas encore vus par toi."""
    members = [u for u in partners(ctx) if not only or u.id in only]
    if not members:
        return []
    media_types = ["movie", "tv"] if media_type == "all" else [media_type]
    mine = set(_loved(ctx, None, media_types))
    excluded = await excluded_keys(ctx)
    scores: dict[tuple[str, int], float] = {}
    names: dict[tuple[str, int], list[str]] = {}
    for u in members:
        theirs = _loved(ctx, u.id, media_types)
        similarity = len(mine & set(theirs)) / (len(mine | set(theirs)) or 1)  # goûts communs (Jaccard)
        for k, s in theirs.items():
            if k in excluded:
                continue
            scores[k] = scores.get(k, 0) + s["weight"] * (0.3 + similarity)
            names.setdefault(k, []).append(u.name)
    ranked = sorted(scores, key=scores.get, reverse=True)[:limit]
    items = await refs_to_items(ctx, [{"media_type": mt, "tmdb_id": tid} for mt, tid in ranked])
    for i in items:
        i.update(_reason("Aimé par {names}", {"names": ", ".join(names.get((i["media_type"], i["id"]), []))}))
    return await enrich(ctx, items)


async def common_watchlist(ctx: Ctx, uids: list[int]) -> list[dict]:
    """Titres dans la watchlist de chacun (toi et les membres choisis), que personne n'a vus."""
    def wl(q) -> set:
        return {(r.media_type, r.tmdb_id) for r in ctx.db.execute(q).scalars() if r.in_watchlist and not r.watched}

    both = wl(_of(MediaState, None))
    for uid in uids:
        both &= wl(_of(MediaState, uid))
    items = await refs_to_items(ctx, [{"media_type": mt, "tmdb_id": tid} for mt, tid in both])
    key = "Dans vos deux watchlists" if len(uids) == 1 else "Dans toutes vos watchlists"
    for i in items:
        i.update(_reason(key))
    return await enrich(ctx, items)


async def together(ctx: Ctx, members: list[tuple[int, str]], media_type: str = "all", limit: int = 40) -> list[dict]:
    """Suggestions pour une soirée à plusieurs (toi et les membres choisis) : recommandations tirées des goûts de
    chacun ; un titre qui plairait à tout le monde passe devant. Rien de déjà vu ou rejeté par l'un d'eux."""
    media_types = ["movie", "tv"] if media_type == "all" else [media_type]
    excluded = await excluded_keys(ctx)
    for uid, _ in members:
        excluded |= unwanted(ctx, uid)
    people = [(None, None)] + list(members)  # None : toi
    per: list[dict] = []
    items: dict[tuple[str, int], dict] = {}
    origin: dict[tuple[str, int], str] = {}
    for uid, name in people:
        seed_list = seeds(ctx, media_types, uid)[0]
        scores: dict = {}
        recs = await asyncio.gather(*(_safe(ctx.tmdb.recommendations(s["media_type"], s["tmdb_id"]), []) for s in seed_list))
        for s, lst in zip(seed_list, recs):
            for rank, item in enumerate(lst[:15]):
                k = (item["media_type"], item["id"])
                if k in excluded:
                    continue
                score = s["weight"] * (15 - rank) / 15
                if score > scores.get(k, 0):
                    scores[k] = score
                    if uid is None:
                        reason = _reason("Parce que tu as aimé {title}", {"title": s["title"]}) if s.get("title") else _reason("Pour toi")
                    elif s.get("title"):
                        reason = _reason("Parce que {name} a aimé {title}", {"name": name, "title": s["title"]})
                    else:
                        reason = _reason("D’après les goûts de {name}", {"name": name})
                    items.setdefault(k, {**item, **reason})
                    origin.setdefault(k, f"{uid}:{s['tmdb_id']}")
        per.append(scores)
    n = len(per)
    final = {}
    for k in items:
        values = [p[k] for p in per if p.get(k)]
        coverage = len(values) / n
        final[k] = (sum(values) / len(values)) * coverage ** 2 * (2 if len(values) == n else 1) * _quality(items[k])
        if len(values) == n:  # plairait à tout le monde
            items[k].update(_reason("Pour vous deux" if n == 2 else "Pour vous tous"))
    ranked = sorted(items, key=final.get, reverse=True)
    pool = [items[k] for k in _variety(ranked, items, origin)][:limit]
    return await enrich(ctx, pool)
