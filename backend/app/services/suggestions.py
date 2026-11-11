"""Moteur de suggestions : likes du mode swipe + historique/notes Trakt + recommandations TMDB."""

import asyncio
import logging
import math
import random
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.models import MediaState, SuggestionFeedback, SuggestionShown, SwipeHistory, WatchEvent
from app.services.clock import utcnow
from app.services.cache import MISS, cache
from app.services.context import Ctx
from app.services.enrich import enrich, refs_to_items
from app.services.errors import ServiceError

log = logging.getLogger(__name__)


async def _safe(coro, default):
    try:
        return await coro
    except ServiceError as e:
        log.info("suggestions: %s", e.message)
        return default


def swipe_keys(ctx: Ctx, actions: tuple[str, ...] | None = None) -> set[tuple[str, int]]:
    q = select(SwipeHistory.media_type, SwipeHistory.tmdb_id)
    if actions:
        q = q.where(SwipeHistory.action.in_(actions))
    return {(mt, tid) for mt, tid in ctx.db.execute(q).all()}


async def excluded_keys(ctx: Ctx) -> set[tuple[str, int]]:
    """Titres à ne jamais proposer : déjà swipés, déjà vus ou déjà en watchlist (tous services)."""
    keys = swipe_keys(ctx)
    keys |= {(mt, tid) for mt, tid in ctx.db.execute(select(SuggestionFeedback.media_type, SuggestionFeedback.tmdb_id)).all()}
    for r in ctx.db.execute(select(MediaState)).scalars():
        if r.in_watchlist or r.watched or r.disliked:
            keys.add((r.media_type, r.tmdb_id))
    if ctx.trakt:
        keys |= await _safe(ctx.trakt.watched_keys(), set())
    return keys


def _caught_up(raw: dict, last_seen: tuple[int, int] | None, seen_on: str | None) -> bool:
    """Série vue et à jour : pas d'épisode sorti que l'on n'a pas encore vu.

    - Historique des épisodes (Plex, Trakt) : à jour si le dernier épisode diffusé a été atteint.
    - Sinon, date du dernier visionnage : à jour si rien n'est sorti depuis.
    - Sans aucune date : à jour seulement si la série est terminée ou annulée."""
    last = raw.get("last_episode_to_air") or {}
    if not last.get("air_date"):
        return True  # rien de diffusé
    aired = (last.get("season_number") or 0, last.get("episode_number") or 0)
    if last_seen and aired[0] > 0:
        return last_seen >= aired
    if seen_on:
        return seen_on[:10] >= last["air_date"]
    return raw.get("status") in ("Ended", "Canceled")


async def seen_keys(ctx: Ctx) -> set[tuple[str, int]]:
    """Titres à ne plus proposer (réglage « déjà vus ») : films vus, séries vues et à jour."""
    # Empreinte de l'état « vu » : la liste est recalculée dès qu'un titre ou un épisode change
    stamp = (
        ctx.db.execute(select(func.count(MediaState.id), func.max(MediaState.updated_at))).one(),
        ctx.db.execute(select(func.count(WatchEvent.id), func.max(WatchEvent.watched_at))).one(),
    )
    key = ("seen-keys", ctx.user.id, str(stamp))
    if (hit := cache.get(key)) is not MISS:
        return hit
    out: set[tuple[str, int]] = set()
    seen_on: dict[int, str | None] = {}
    for r in ctx.db.execute(select(MediaState).where(MediaState.watched_sources != "[]")).scalars():
        if r.media_type == "movie":
            out.add(("movie", r.tmdb_id))
        else:
            seen_on[r.tmdb_id] = r.watched_at
    # Dernier épisode vu de chaque série (saisons spéciales exclues) et date du dernier visionnage
    last_ep: dict[int, tuple[int, int]] = {}
    q = select(WatchEvent.tmdb_id, WatchEvent.season, WatchEvent.episode, WatchEvent.watched_at).where(
        WatchEvent.kind == "episode", WatchEvent.tmdb_id.isnot(None)
    )
    for tid, season, episode, at in ctx.db.execute(q):
        if season and episode is not None:
            last_ep[tid] = max(last_ep.get(tid, (0, 0)), (season, episode))
        when = at.isoformat() if at else None
        if when and (not seen_on.get(tid) or when > seen_on[tid]):
            seen_on[tid] = when
    sem = asyncio.Semaphore(8)

    async def check(tid: int) -> None:
        async with sem:
            try:
                raw = await ctx.tmdb._get(f"/tv/{tid}", ttl=21600)
            except ServiceError:
                return  # en cas de doute, la série reste proposée
        if _caught_up(raw, last_ep.get(tid), seen_on.get(tid)):
            out.add(("tv", tid))

    if not ctx.tmdb.is_mock:
        await asyncio.gather(*(check(tid) for tid in seen_on))
    cache.set(key, out, 1800)
    return out


async def watchlist_releases(ctx: Ctx, days: int, cached_only: bool = False) -> list[dict] | None:
    """Titres de la watchlist (pas encore vus) sortis ces `days` derniers jours, du plus récent au plus ancien.

    Film : sortie en salles (ou ressortie) ou en VOD / streaming dans le pays (date mondiale si le pays n'en
    a pas). Série : dernier épisode diffusé (nouvelle série, nouvelle saison ou nouvel épisode).
    Une requête TMDB par titre (en cache) : la tâche périodique `warm_releases` garde le résultat prêt.
    cached_only : None si pas encore calculé (le carrousel n'attend pas)."""
    if days <= 0 or ctx.tmdb.is_mock:
        return []
    rows = [r for r in ctx.db.execute(select(MediaState)).scalars() if r.in_watchlist and not r.watched and not r.disliked]
    stamp = (len(rows), max((r.updated_at for r in rows if r.updated_at), default=None))
    key = ("watchlist-releases", ctx.user.id, days, date.today().isoformat(), str(stamp))
    if (hit := cache.get(key)) is not MISS:
        return hit
    if cached_only:
        return None
    start, end = (date.today() - timedelta(days=days)).isoformat(), date.today().isoformat()
    sem = asyncio.Semaphore(16)

    async def one(r: MediaState) -> dict | None:
        async with sem:
            try:
                if r.media_type == "movie":
                    dates = await ctx.tmdb.release_dates(r.tmdb_id)
                    first = min(dates["cinema"], default="")
                    # Ressortie : sortie en salles plus d'un an après la première
                    old = lambda d: first and first < (date.fromisoformat(d) - timedelta(days=365)).isoformat()  # noqa: E731
                    found = [(d, "Ressortie au cinéma" if old(d) else "Sorti au cinéma") for d in dates["cinema"] if start <= d <= end]
                    found += [(d, "Sorti en VOD / streaming") for d in dates["streaming"] if start <= d <= end]
                    item = None
                    if not found and not dates["cinema"] and not dates["streaming"]:
                        item = await ctx.tmdb.basic("movie", r.tmdb_id)  # pas de date pour le pays : date mondiale
                        d = (item or {}).get("release_date") or ""
                        found = [(d, "Sorti au cinéma")] if start <= d <= end else []
                    if not found:
                        return None
                    released, reason = max(found)
                    item = item or await ctx.tmdb.basic("movie", r.tmdb_id)
                else:
                    raw = await ctx.tmdb._get(f"/tv/{r.tmdb_id}", ttl=21600)
                    last = raw.get("last_episode_to_air") or {}
                    released = last.get("air_date") or ""
                    if not start <= released <= end:
                        return None
                    s, e = last.get("season_number"), last.get("episode_number")
                    reason = "Nouvelle série" if (s, e) == (1, 1) else "Nouvelle saison" if e == 1 else "Nouvel épisode"
                    item = await ctx.tmdb.basic("tv", r.tmdb_id)
            except ServiceError:
                return None  # une source indisponible ne bloque pas les autres titres
        return {**item, "reason": reason, "released_on": released} if item else None

    found = [x for x in await asyncio.gather(*(one(r) for r in rows)) if x]
    found.sort(key=lambda i: i["released_on"], reverse=True)
    cache.set(key, found, 6 * 3600)
    return found


SEEDS_TOP, SEEDS_ROTATING = 20, 20  # références : les plus fortes, puis un tirage qui change chaque jour
PER_SEED = 3  # suggestions au plus par référence (variété)
MIN_DISCOVERY = 0.3  # part minimale de titres hors de tes plateformes et de ta bibliothèque, pour continuer à découvrir
AVAILABLE_BOOST = 1.35  # ce que tu peux regarder remonte, sans écarter le reste


def _age_days(when) -> float:
    if not when:
        return 365.0
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return 365.0
    return max(0.0, (utcnow() - when).total_seconds() / 86400)


def _decay(when) -> float:
    """Poids d'un signal selon son ancienneté : moitié tous les 8 mois, jamais moins d'un tiers."""
    return max(0.35, 0.5 ** (_age_days(when) / 240))


def _of(model, user_id: int | None):
    """Requête sur les données du compte courant, ou d'un autre compte (fonctions famille, avec son accord)."""
    q = select(model)
    return q.where(model.user_id == user_id).execution_options(all_users=True) if user_id is not None else q


def signals(ctx: Ctx, media_types: list[str], user_id: int | None = None) -> tuple[list[dict], list[dict]]:
    """Tout ce que SynCiné sait de tes goûts (aucune requête externe), du plus fort au plus faible : titres aimés et
    titres rejetés. Sources : coups de cœur et notes (Trakt, Plex, Letterboxd, SynCiné), « plus / moins comme ça »,
    mode swipe, watchlist, historique de visionnage (Plex, Jellyfin, Trakt, Letterboxd), pondérés par l'ancienneté."""
    pos: dict[tuple[str, int], dict] = {}
    neg: dict[tuple[str, int], dict] = {}

    def add(table: dict, mt: str, tid: int | None, title: str, weight: float, when=None, loved: bool = False) -> None:
        # loved : avis explicite (coup de cœur, bonne note, « J'aime », « plus comme ça ») — le seul signal qu'un
        # autre compte peut lire quand les goûts sont partagés (voir services/family.py)
        if not tid or mt not in media_types or weight <= 0:
            return
        w = weight * _decay(when)
        cur = table.get((mt, tid))
        if cur is None:
            table[(mt, tid)] = {"media_type": mt, "tmdb_id": tid, "title": title or "", "weight": w, "signals": 1, "loved": loved}
        else:  # plusieurs signaux pour un même titre : le plus fort, plus un petit bonus
            cur["weight"] = max(cur["weight"], w) + 0.15
            cur["signals"] += 1
            cur["title"] = cur["title"] or title or ""
            cur["loved"] = cur["loved"] or loved

    for r in ctx.db.execute(_of(MediaState, user_id)).scalars():
        when = r.watched_at or r.listed_at or r.updated_at
        if r.disliked:
            add(neg, r.media_type, r.tmdb_id, r.title, 1.0, r.updated_at)
            continue
        if r.liked:
            add(pos, r.media_type, r.tmdb_id, r.title, 1.5, when, loved=True)
        if r.rating is not None:
            if r.rating >= 8:
                add(pos, r.media_type, r.tmdb_id, r.title, 1.0 + (r.rating - 7) * 0.25, when, loved=True)
            elif r.rating <= 4:
                add(neg, r.media_type, r.tmdb_id, r.title, 0.6 + (4 - r.rating) * 0.2, when)
        elif r.watched:
            add(pos, r.media_type, r.tmdb_id, r.title, 0.5, when)
        if r.in_watchlist:
            add(pos, r.media_type, r.tmdb_id, r.title, 0.5, r.listed_at)
    for r in ctx.db.execute(_of(SwipeHistory, user_id).where(SwipeHistory.action.in_(("like", "watchlist", "seen")))).scalars():
        weight = {"like": 1.5, "watchlist": 0.8}.get(r.action, 1.0 if (r.rating or 0) >= 4 else 0)
        add(pos, r.media_type, r.tmdb_id, r.title, weight, r.created_at, loved=r.action == "like")
    for r in ctx.db.execute(_of(SuggestionFeedback, user_id)).scalars():
        add(pos if r.value > 0 else neg, r.media_type, r.tmdb_id, r.title, 1.3 if r.value > 0 else 1.0, r.created_at, loved=r.value > 0)
    # Historique : films vus, séries suivies (plus d'épisodes vus, plus de poids)
    since = utcnow() - timedelta(days=365)
    q = (
        select(WatchEvent.kind, WatchEvent.tmdb_id, func.count(), func.max(WatchEvent.watched_at), func.max(WatchEvent.title), func.max(WatchEvent.show_title))
        .where(WatchEvent.tmdb_id.isnot(None), WatchEvent.watched_at >= since)
        .group_by(WatchEvent.kind, WatchEvent.tmdb_id)
    )
    if user_id is not None:
        q = q.where(WatchEvent.user_id == user_id).execution_options(all_users=True)
    rows = ctx.db.execute(q).all()
    for kind, tid, n, last, title, show in rows:
        if kind == "movie":
            add(pos, "movie", tid, title, 0.8, last)
        else:
            add(pos, "tv", tid, show, 0.6 + min(n, 10) * 0.06, last)

    return sorted(pos.values(), key=lambda s: s["weight"], reverse=True), sorted(neg.values(), key=lambda s: s["weight"], reverse=True)


def seeds(ctx: Ctx, media_types: list[str], user_id: int | None = None, loved_only: bool = False) -> tuple[list[dict], list[dict]]:
    """Références pour les recommandations : les plus fortes, plus un tirage pondéré qui change chaque jour (pour
    renouveler les suggestions) ; et les 3 titres les plus rejetés. loved_only : seulement les avis explicites
    (références d'un autre compte qui partage ses goûts)."""
    ranked, negatives = signals(ctx, media_types, user_id)
    if loved_only:
        ranked = [s for s in ranked if s["loved"]]
    top, rest = ranked[:SEEDS_TOP], ranked[SEEDS_TOP:SEEDS_TOP + 3 * SEEDS_ROTATING]
    rng = random.Random(f"{user_id or ctx.user.id}-{date.today().isoformat()}")  # même tirage toute la journée
    rotating = []
    while rest and len(rotating) < SEEDS_ROTATING:
        pick = rng.choices(rest, weights=[s["weight"] for s in rest])[0]
        rotating.append(pick)
        rest.remove(pick)
    return top + rotating, negatives[:3]


def _franchise(title: str) -> str:
    """Clé de saga approximative : titre avant « : », sans numéro final (« Dune », « Dune : Deuxième partie »)."""
    t = re.split(r"\s*[:–-]\s+", (title or "").lower(), maxsplit=1)[0]
    t = re.sub(r"\s+(\d+|[ivx]+|part \w+|partie \w+)$", "", t.strip())
    return t.strip()


def _variety(ranked: list[tuple[str, int]], items: dict, origin: dict) -> list[tuple[str, int]]:
    """Au plus PER_SEED suggestions par référence, et une seule par saga."""
    per_seed: dict = {}
    sagas: set[str] = set()
    out = []
    for k in ranked:
        seed, saga = origin.get(k), _franchise(items[k].get("title") or "")
        if (seed and per_seed.get(seed, 0) >= PER_SEED) or (saga and saga in sagas):
            continue
        per_seed[seed] = per_seed.get(seed, 0) + 1
        sagas.add(saga)
        out.append(k)
    return out


def _mix_types(ordered: list[dict], media_types: list[str]) -> list[dict]:
    """Films et séries mélangés : à chaque place, le meilleur suivant, sauf si son type dépasserait 65 % de la liste."""
    if len(media_types) < 2:
        return ordered
    queues = {mt: [i for i in ordered if i["media_type"] == mt] for mt in media_types}
    out: list[dict] = []
    while any(queues.values()):
        heads = [q[0] for q in queues.values() if q]
        best = min(heads, key=ordered.index)
        other = [mt for mt in media_types if mt != best["media_type"] and queues[mt]]
        if out and other and sum(1 for i in out if i["media_type"] == best["media_type"]) + 1 > 0.65 * (len(out) + 1):
            best = queues[other[0]][0]
        queues[best["media_type"]].remove(best)
        out.append(best)
    return out


RECENT_BOOST = 3.0  # titre sorti depuis moins d'un an
RECENT_PAGES = 2  # sorties de l'année ajoutées aux candidats : pages de 20 titres, par type
RECENT_SCORE = 0.5  # leur score de départ (une recommandation d'une référence forte vaut 1 à 2)
RECENT_GROUPS = 1  # plafond de ces sorties dans la liste : PER_SEED x RECENT_GROUPS par type (0 : sans plafond)


def _prior(item: dict) -> float:
    """Intérêt a priori d'un candidat, avant les goûts : sortie récente, titre connu, bien noté.

    Mesuré sur des historiques réels (banc hors ligne à coupure temporelle, voir docs/wiki/03-backend.md) : parmi les titres que TMDB recommande, ceux qui
    sont regardés ensuite sont six fois plus souvent sortis dans l'année ; presque aucun n'a moins de 100 votes ou
    une note sous 6. La popularité est volontairement adoucie (puissance 0,4) pour laisser remonter des découvertes."""
    votes, avg = item.get("vote_count") or 0, item.get("vote_average") or 0
    try:
        age = (date.today() - date.fromisoformat(item.get("release_date") or "")).days / 365
    except ValueError:
        age = None
    recent = 1.0 if age is None or age < 0 else RECENT_BOOST if age < 1 else 1.0 if age < 10 else 0.8
    known = (max(votes, 20) / 1500) ** 0.4
    rated = min(4.5, max(0.15, math.exp(1.2 * (avg - 7)))) if avg else 0.5
    return recent * known * rated


def _available(item: dict, platforms: set[int]) -> bool:
    return bool(item.get("in_plex")) or any(p.get("id") in platforms for p in item.get("providers") or [])


def _keep_discovery(ranked: list[dict], platforms: set[int], limit: int) -> list[dict]:
    """Ce que tu peux regarder passe devant, mais au moins MIN_DISCOVERY de la liste reste de la découverte."""
    out = ranked[:limit]
    want = int(limit * MIN_DISCOVERY + 0.999)
    others = [i for i in ranked[limit:] if not _available(i, platforms)]
    while sum(1 for i in out if not _available(i, platforms)) < want and others:
        last_available = max((n for n, i in enumerate(out) if _available(i, platforms)), default=None)
        if last_available is None:
            break
        out[last_available] = others.pop(0)
    return out


def _reason(key: str, params: dict | None = None) -> dict:
    """Raison affichée : texte français (compatibilité) et clé + variables, traduites par l'interface."""
    text = key.format(**params) if params else key
    return {"reason": text, "reason_key": key, "reason_params": params or {}}


async def _apply_taste(ctx: Ctx, media_types: list[str], pool: list[dict], scores: dict) -> None:
    """Affinité avec le profil de goûts (genres, personnes, mots-clés, langue, époque) : ajuste les scores et donne
    une raison plus parlante quand une personne aimée participe au titre. Trie la liste sur place."""
    if ctx.tmdb.is_mock or not pool:
        return
    from app.services import taste

    pos, neg = signals(ctx, ["movie", "tv"])
    prof = await taste.profile(ctx, pos, neg)
    if prof is None:
        return
    sem = asyncio.Semaphore(8)

    async def one(item):
        async with sem:
            return await taste.features(ctx, item["media_type"], item["id"])

    for item, f in zip(pool, await asyncio.gather(*(one(i) for i in pool))):
        if not f:
            continue
        mult, why = taste.affinity(prof, f, item["media_type"])
        scores[(item["media_type"], item["id"])] *= mult
        if why:
            item.update(_reason(*why))
    pool.sort(key=lambda i: scores[(i["media_type"], i["id"])], reverse=True)


def record_shown(ctx: Ctx, items: list[dict]) -> None:
    """Mémorise les suggestions montrées (au plus une fois toutes les 12 heures par titre)."""
    now = utcnow()
    rows = {(r.media_type, r.tmdb_id): r for r in ctx.db.execute(select(SuggestionShown)).scalars()}
    for i in items:
        r = rows.get((i["media_type"], i["id"]))
        if r is None:
            ctx.db.add(SuggestionShown(media_type=i["media_type"], tmdb_id=i["id"], count=1, last_shown=now))
        elif not r.last_shown or now - r.last_shown >= timedelta(hours=12):
            r.count, r.last_shown = r.count + 1, now
    ctx.db.commit()


async def suggestions(ctx: Ctx, media_type: str = "all", limit: int = 20, with_enrich: bool = True,
                      discovery: bool = True, available_only: bool = False) -> list[dict]:
    """Suggestions classées : recommandations TMDB des références (moins celles des titres mal notés), Trakt,
    titres déjà souvent montrés en retrait, variété, et ce que tu peux regarder en tête.
    discovery : garder une part de titres que tu n'as pas encore (Découvrir) ; available_only : seulement le reste."""
    media_types = ["movie", "tv"] if media_type == "all" else [media_type]
    excluded = await excluded_keys(ctx)
    seed_list, negatives = seeds(ctx, media_types)
    excluded |= {(s["media_type"], s["tmdb_id"]) for s in seed_list}

    scores: dict[tuple[str, int], float] = {}
    items: dict[tuple[str, int], dict] = {}
    origin: dict[tuple[str, int], str] = {}  # référence qui a le plus apporté (variété)

    def add(item: dict, score: float, reason: str, seed: str, params: dict | None = None) -> None:
        k = (item["media_type"], item["id"])
        if k in excluded:
            return
        if k not in items or score > scores.get(k, 0):
            items[k] = {**item, **_reason(reason, params)}
            origin[k] = seed
        scores[k] = scores.get(k, 0) + score

    # 1. Recommandations TMDB à partir des références (et de celles des titres mal notés, en négatif)
    rec_lists, neg_lists = await asyncio.gather(
        asyncio.gather(*(_safe(ctx.tmdb.recommendations(s["media_type"], s["tmdb_id"]), []) for s in seed_list)),
        asyncio.gather(*(_safe(ctx.tmdb.recommendations(s["media_type"], s["tmdb_id"]), []) for s in negatives)),
    )
    for s, recs in zip(seed_list, rec_lists):
        reason, params = ("Parce que tu as aimé {title}", {"title": s["title"]}) if s.get("title") else ("Pour toi", None)
        for rank, item in enumerate(recs[:15]):
            add(item, s["weight"] * (15 - rank) / 15, reason, f"{s['media_type']}:{s['tmdb_id']}", params)
    unwanted = {(i["media_type"], i["id"]) for recs in neg_lists for i in recs[:10]}

    # 2. Recommandations personnalisées Trakt
    if ctx.trakt:
        trakt_refs = []
        for mt in media_types:
            trakt_refs += await _safe(ctx.trakt.recommendations(mt, 15), [])
        trakt_refs = [r for r in trakt_refs if (r["media_type"], r["tmdb_id"]) not in excluded][:12]
        for item in await refs_to_items(ctx, trakt_refs):
            add(item, 1.2, "Recommandé par Trakt", "trakt")

    # 3. Sorties de l'année les plus suivies : une bonne part de ce qui est regardé vient de sortir, et les
    #    recommandations des références n'en font remonter qu'une partie
    if RECENT_PAGES:
        today = date.today()
        since = (today - timedelta(days=365)).isoformat()
        for mt in media_types:
            field = "primary_release_date" if mt == "movie" else "first_air_date"
            window = {f"{field}.gte": since, f"{field}.lte": today.isoformat()}
            pages = await asyncio.gather(*(_safe(ctx.tmdb.discover(mt, page=p, sort_by="vote_count.desc", **window), []) for p in range(1, RECENT_PAGES + 1)))
            for n, item in enumerate(i for page in pages for i in page):
                # Origines réparties en groupes : la règle de variété (PER_SEED par origine) plafonne ainsi leur nombre
                add(item, RECENT_SCORE, "Sortie récente remarquée", f"recent:{mt}:{n % RECENT_GROUPS}" if RECENT_GROUPS else "")

    # 4. Complément : incontournables bien notés
    if len(items) < limit * 2:
        for mt in media_types:
            extra = await _safe(
                ctx.tmdb.discover(mt, page=random.randint(1, 5), sort_by="vote_average.desc", **{"vote_count.gte": 1500}),
                [],
            )
            for item in extra:
                add(item, 0.1, "Incontournable", "classics")

    # Proches de ce que tu n'aimes pas : en retrait ; genres souvent rejetés : pénalité proportionnelle
    for k in unwanted & scores.keys():
        scores[k] *= 0.5
    disliked_rows = list(ctx.db.execute(select(MediaState).where(MediaState.disliked.is_(True))).scalars())[:40]
    if disliked_rows and not ctx.tmdb.is_mock:
        from collections import Counter

        basics = await asyncio.gather(*(_safe(ctx.tmdb.basic(r.media_type, r.tmdb_id), None) for r in disliked_rows))
        bad = Counter(g for b in basics if b for g in b.get("genre_ids", []))
        for k, it in items.items():
            penalty = sum(bad[g] for g in it.get("genre_ids", []) if bad[g] >= 2)
            if penalty:
                scores[k] /= 1 + 0.25 * penalty
    # Déjà montré plusieurs fois sans réaction : descend peu à peu
    shown = {(r.media_type, r.tmdb_id): r.count for r in ctx.db.execute(select(SuggestionShown)).scalars()}
    for k in scores:
        if shown.get(k, 0) > 2:
            scores[k] /= 1 + 0.35 * (shown[k] - 2)

    for k, it in items.items():
        scores[k] *= _prior(it)
    ranked = sorted(items, key=lambda k: scores[k], reverse=True)
    pool = [items[k] for k in _variety(ranked, items, origin)][: limit * 2]
    await _apply_taste(ctx, media_types, pool, scores)
    if not with_enrich:
        return _mix_types(pool, media_types)[:limit]
    pool = await enrich(ctx, pool)
    # Ce que tu peux regarder (plateformes, bibliothèque) remonte, puis films et séries sont mélangés
    platforms = set(ctx.platforms)
    boosted = sorted(pool, key=lambda i: scores[(i["media_type"], i["id"])] * (AVAILABLE_BOOST if _available(i, platforms) else 1), reverse=True)
    if available_only:
        return _mix_types([i for i in boosted if _available(i, platforms)], media_types)[:limit]
    ordered = _mix_types(boosted, media_types)
    return _keep_discovery(ordered, platforms, limit) if discovery else ordered[:limit]
