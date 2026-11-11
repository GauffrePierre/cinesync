"""Profil de goûts : genres, mots-clés, réalisateurs ou créateurs, acteurs, langues et décennies des titres aimés
(et, en négatif, des titres mal notés), d'après les fiches TMDB (en cache 6 h, partagées entre comptes).

Sert à classer les suggestions (affinité) et à expliquer pourquoi un titre est proposé (« Réalisé par … »).
Le profil d'un compte est gardé 6 h ; la tâche périodique des sorties de la watchlist le prépare d'avance."""

import asyncio
from collections import Counter
from dataclasses import dataclass, field

from app.services.cache import MISS, cache
from app.services.context import Ctx
from app.services.errors import ServiceError

TOP_POSITIVE, TOP_NEGATIVE = 60, 20
MIN_TITLES = 5  # en dessous, pas assez de données : pas d'ajustement


@dataclass
class Profile:
    titles: int = 0
    genres: Counter = field(default_factory=Counter)  # id -> poids (positif : aimé, négatif : rejeté)
    keywords: Counter = field(default_factory=Counter)
    makers: Counter = field(default_factory=Counter)  # réalisateurs (films) et créateurs (séries)
    cast: Counter = field(default_factory=Counter)
    langs: Counter = field(default_factory=Counter)
    decades: Counter = field(default_factory=Counter)
    names: dict = field(default_factory=dict)  # id de personne -> nom


FEATURES_TTL = 7 * 86400  # genres, équipe et mots-clés d'un titre ne changent presque jamais


async def features(ctx: Ctx, media_type: str, tmdb_id: int) -> dict | None:
    """Caractéristiques d'un titre, gardées une semaine (quelques centaines d'octets, au lieu de la fiche entière)."""
    key = ("tmdb", "features", media_type, tmdb_id)
    if (hit := cache.get(key)) is not MISS:
        return hit
    try:
        raw = await ctx.tmdb.features_raw(media_type, tmdb_id)
    except ServiceError:
        return None
    if not raw:
        return None
    kw = raw.get("keywords") or {}
    credits = raw.get("credits") or {}
    cast = (credits.get("cast") or (raw.get("aggregate_credits") or {}).get("cast") or [])[:6]
    makers = [c for c in credits.get("crew") or [] if c.get("job") == "Director"] if media_type == "movie" else raw.get("created_by") or []
    year = (raw.get("release_date") or raw.get("first_air_date") or "")[:4]
    out = {
        "genres": [g["id"] for g in raw.get("genres") or []],
        "keywords": [k["id"] for k in (kw.get("keywords") or kw.get("results") or [])[:15]],
        "makers": {m["id"]: m.get("name") or "" for m in makers[:3]},
        "cast": {c["id"]: c.get("name") or "" for c in cast},
        "lang": raw.get("original_language"),
        "decade": int(year) // 10 * 10 if year.isdigit() else None,
    }
    cache.set(key, out, FEATURES_TTL)
    return out


async def profile(ctx: Ctx, positives: list[dict], negatives: list[dict]) -> Profile | None:
    """Profil du compte à partir de ses références (voir suggestions.signals), gardé 6 h."""
    key = ("taste", ctx.user.id, len(positives), len(negatives))
    if (hit := cache.get(key)) is not MISS:
        return hit
    pos = sorted(positives, key=lambda s: s["weight"], reverse=True)[:TOP_POSITIVE]
    neg = sorted(negatives, key=lambda s: s["weight"], reverse=True)[:TOP_NEGATIVE]
    sem = asyncio.Semaphore(8)

    async def one(s):
        async with sem:
            return await features(ctx, s["media_type"], s["tmdb_id"])

    feats = await asyncio.gather(*(one(s) for s in pos + neg))
    p = Profile()
    for s, f in zip(pos + neg, feats):
        if not f:
            continue
        w = s["weight"] if s in pos else -1.5 * s["weight"]
        p.titles += 1 if w > 0 else 0
        for g in f["genres"]:
            p.genres[g] += w
        if w > 0:  # personnes, mots-clés, langues, décennies : seulement ce qui est aimé
            for k in f["keywords"]:
                p.keywords[k] += w
            for pid, name in f["makers"].items():
                p.makers[pid] += w
                p.names[pid] = name
            for pid, name in f["cast"].items():
                p.cast[pid] += w
                p.names[pid] = name
            if f["lang"]:
                p.langs[f["lang"]] += w
            if f["decade"]:
                p.decades[f["decade"]] += w
    p = p if p.titles >= MIN_TITLES else None
    cache.set(key, p, 6 * 3600)
    return p


def affinity(p: Profile, f: dict, media_type: str) -> tuple[float, tuple[str, dict] | None]:
    """Coefficient d'affinité (0,5 à 1,8) et, si une personne aimée y participe, une raison à afficher."""
    mult, reason = 1.0, None
    top = max((abs(v) for v in p.genres.values()), default=0) or 1
    if f["genres"]:
        mult *= 1 + 0.35 * sum(p.genres.get(g, 0) / top for g in f["genres"]) / len(f["genres"])
    maker = max(f["makers"], key=lambda pid: p.makers.get(pid, 0), default=None)
    if maker and p.makers.get(maker, 0) >= 1.5:  # au moins un ou deux titres aimés de cette personne
        mult *= 1.3
        key = "Réalisé par {name}, que tu aimes" if media_type == "movie" else "Créée par {name}, que tu aimes"
        reason = (key, {"name": p.names.get(maker) or f["makers"][maker]})
    actors = [pid for pid in f["cast"] if p.cast.get(pid, 0) >= 2]  # présent dans plusieurs coups de cœur
    if actors:
        mult *= min(1.25, 1 + 0.1 * len(actors))
        if not reason:
            best = max(actors, key=lambda pid: p.cast[pid])
            reason = ("Avec {name}, souvent dans tes coups de cœur", {"name": p.names.get(best) or f["cast"][best]})
    matches = sum(1 for k in f["keywords"] if p.keywords.get(k, 0) >= 1)
    mult *= 1 + min(0.2, 0.04 * matches)
    total_lang = sum(p.langs.values()) or 1
    share = p.langs.get(f["lang"], 0) / total_lang
    mult *= 1.05 if share >= 0.15 else (0.9 if share == 0 and p.titles >= 10 else 1)
    total_dec = sum(p.decades.values()) or 1
    if f["decade"] and p.decades.get(f["decade"], 0) / total_dec >= 0.2:
        mult *= 1.05
    return max(0.5, min(1.8, mult)), reason
