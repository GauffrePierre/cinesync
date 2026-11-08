"""Synchronisation de l'état personnel (watchlist, vu, notes, j'aime) entre tous les services.

pull()      collecte l'existant sur Trakt, Plex (compte + serveur), Letterboxd et les swipes,
            et le fusionne dans la table media_state (sauvegarde locale).
act()       applique une action faite dans CinéSync à chaque service capable de la stocker,
            puis l'enregistre localement — même si un service est en panne.
_two_way() synchronisation automatique : watchlists identiques des deux côtés (ajouts et retraits),
            vus et notes recopiés là où ils manquent, avec garde-fous (voir la fonction).
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import MediaState, SwipeHistory
from app.services.context import Ctx
from app.services.errors import ServiceError

log = logging.getLogger(__name__)

RATING_PRIORITY = ("trakt", "plex", "letterboxd", "local")
# Par compte : dernier résultat et verrou (deux synchronisations du même compte ne se chevauchent pas)
_last_pull: dict[int, dict] = {}
_pull_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _uid(ctx) -> int:
    return getattr(getattr(ctx, "user", None), "id", None) or 1


EMPTY_STATE = {
    "in_watchlist": False, "watchlist_sources": [], "watched": False, "watched_sources": [],
    "rating": None, "rating_source": None, "liked": False, "disliked": False, "listed_at": None, "watched_at": None,
}


def state_of(db, media_type: str, tmdb_id: int) -> dict:
    row = get_row(db, media_type, tmdb_id, create=False)
    return row.state() if row else dict(EMPTY_STATE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_row(db, media_type: str, tmdb_id: int, create: bool = True, **info) -> MediaState | None:
    row = db.execute(select(MediaState).where(MediaState.tmdb_id == tmdb_id, MediaState.media_type == media_type)).scalar_one_or_none()
    if row is None and create:
        row = MediaState(tmdb_id=tmdb_id, media_type=media_type)
        db.add(row)
    if row is not None:
        for k in ("title", "year", "poster"):
            if info.get(k) and not getattr(row, k):
                setattr(row, k, info[k])
    return row


def last_pull(ctx) -> dict:
    return _last_pull.get(_uid(ctx), {})


async def preview(ctx: Ctx) -> dict:
    """Ce que ferait la synchronisation bidirectionnelle, sans rien écrire."""
    collected = await _collect(ctx)
    rows = {(r.media_type, r.tmdb_id): r for r in ctx.db.execute(select(MediaState)).scalars()}
    prev = {k: r.sources("watchlist") for k, r in rows.items()}
    plan = await _two_way(ctx, collected, rows, prev, dry_run=True)
    ctx.db.rollback()  # aucune modification locale non plus
    return plan


# --- Collecte --------------------------------------------------------------------


async def _collect(ctx: Ctx) -> dict[str, dict]:
    """Lit chaque service. Renvoie {source: {"watchlist": {...}, "watched": {...}, "ratings": {...}, "info": {...}}}
    ou {"error": msg} pour un service en panne (ses données locales sont alors conservées)."""

    async def trakt():
        wl, watched, ratings = await asyncio.gather(ctx.trakt.watchlist(), ctx.trakt.watched_keys(), ctx.trakt.ratings())
        return {
            "watchlist": {(r["media_type"], r["tmdb_id"]): r.get("listed_at") for r in wl},
            "watched": {k: None for k in watched},
            "ratings": {(r["media_type"], r["tmdb_id"]): r["rating"] for r in ratings},
            "info": {(r["media_type"], r["tmdb_id"]): r for r in wl + ratings},
        }

    async def plex():
        out = {"watchlist": {}, "watched": {}, "ratings": {}, "info": {}}
        if ctx.plex_account:
            # Plex ne donne pas la date d'ajout, mais renvoie la watchlist triée du plus récent
            # au plus ancien : on reconstitue un ordre (dates décroissantes d'une seconde)
            base = datetime.now(timezone.utc)
            for idx, r in enumerate(await ctx.plex_account.watchlist()):
                k = (r["media_type"], r["tmdb_id"])
                out["watchlist"][k] = (base - timedelta(seconds=idx)).isoformat()
                out["info"][k] = r
        if ctx.plex_own:
            for i in await ctx.plex_own.library():
                if not i.get("id"):
                    continue
                k = (i["media_type"], i["id"])
                if i["media_type"] == "movie":
                    seen = bool(i.get("view_count"))
                else:  # série : entièrement vue seulement
                    seen = bool(i.get("episodes")) and i.get("viewed_episodes") == i.get("episodes")
                if seen:
                    out["watched"][k] = i.get("last_viewed_at")
                if i.get("user_rating"):
                    out["ratings"][k] = i["user_rating"]
                out["info"].setdefault(k, {"title": i.get("title"), "year": i.get("year")})
        return out

    async def letterboxd():
        diary = await ctx.letterboxd.diary()
        entries = [d for d in diary if d.get("tmdb_id")]
        return {
            "watchlist": None,  # Letterboxd ne fournit pas la watchlist par RSS
            "watched": {("movie", d["tmdb_id"]): d.get("watched_date") for d in entries},
            "ratings": {("movie", d["tmdb_id"]): round(d["rating"] * 2) for d in entries if d.get("rating")},
            "info": {("movie", d["tmdb_id"]): {"title": d["title"], "year": d.get("year"), "poster": d.get("poster")} for d in entries},
        }

    jobs = {}
    if ctx.trakt:
        jobs["trakt"] = trakt()
    if ctx.plex_account or ctx.plex_own:
        jobs["plex"] = plex()
    if ctx.letterboxd:
        jobs["letterboxd"] = letterboxd()

    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    out = {}
    for name, res in zip(jobs, results):
        if isinstance(res, ServiceError):
            out[name] = {"error": res.message}
        elif isinstance(res, Exception):
            log.exception("Collecte %s", name, exc_info=res)
            out[name] = {"error": f"Erreur inattendue : {res.__class__.__name__}"}
        else:
            out[name] = res
    return out


def _import_swipes(ctx: Ctx, rows: dict) -> None:
    """Les swipes passés deviennent des données locales (j'aime, vu, note, watchlist)."""
    for sw in ctx.db.execute(select(SwipeHistory)).scalars():
        if sw.action == "skip":
            continue
        k = (sw.media_type, sw.tmdb_id)
        row = rows.get(k) or get_row(ctx.db, sw.media_type, sw.tmdb_id, title=sw.title)
        rows[k] = row
        if sw.action in ("like", "watchlist"):
            row.add_source("watchlist", "local")
        if sw.action == "like":
            row.liked = True
        if sw.action == "seen":
            row.add_source("watched", "local")
            if sw.rating and not row.rating:
                row.rating, row.rating_source = sw.rating * 2, "local"


async def pull(ctx: Ctx) -> dict:
    async with _pull_locks[_uid(ctx)]:
        started = now_iso()
        collected = await _collect(ctx)
        rows = {(r.media_type, r.tmdb_id): r for r in ctx.db.execute(select(MediaState)).scalars()}
        # État au moment de la synchronisation précédente : permet de distinguer un ajout d'un retrait
        prev_watchlist = {k: r.sources("watchlist") for k, r in rows.items()}

        summary = {}
        for source, data in collected.items():
            if "error" in data:
                summary[source] = {"ok": False, "error": data["error"]}
                continue
            counts = {}
            for field in ("watchlist", "watched"):
                keys = data.get(field)
                if keys is None:
                    continue
                counts[field] = len(keys)
                # Remplacement : la source fait foi pour ce qu'elle contient
                for k, row in rows.items():
                    if k not in keys and source in row.sources(field):
                        row.remove_source(field, source)
                for k, when in keys.items():
                    info = data["info"].get(k, {})
                    row = rows.get(k) or get_row(ctx.db, k[0], k[1], title=info.get("title"), year=info.get("year"), poster=info.get("poster"))
                    rows[k] = row
                    row.add_source(field, source)
                    if field == "watchlist" and when and not row.listed_at:
                        row.listed_at = when
                    if field == "watched" and when and (not row.watched_at or when > row.watched_at):
                        row.watched_at = when
            # Titres notés mais ni en watchlist ni vus : il leur faut aussi une ligne, sinon la note serait perdue
            for k in data.get("ratings", {}):
                if k not in rows:
                    info = data["info"].get(k, {})
                    rows[k] = get_row(ctx.db, k[0], k[1], title=info.get("title"), year=info.get("year"), poster=info.get("poster"))
            counts["ratings"] = len(data.get("ratings", {}))
            summary[source] = {"ok": True, **counts}

        # Notes : la source la plus prioritaire qui a une note l'emporte
        ratings = {s: d.get("ratings", {}) for s, d in collected.items() if "error" not in d}
        failed = {s for s, d in collected.items() if "error" in d}
        for k, row in rows.items():
            for src in RATING_PRIORITY:
                if src in ratings and k in ratings[src]:
                    row.rating, row.rating_source = ratings[src][k], src
                    break
            else:
                if row.rating_source and row.rating_source not in failed and row.rating_source != "local":
                    row.rating, row.rating_source = None, ""

        _import_swipes(ctx, rows)
        ctx.db.commit()

        # Affiches manquantes pour la watchlist (en tâche de fond, sans bloquer)
        missing = [r for r in rows.values() if r.in_watchlist and not r.poster][:200]
        if missing and not ctx.tmdb.is_mock:
            sem = asyncio.Semaphore(8)

            async def fill(r: MediaState):
                async with sem:
                    try:
                        b = await ctx.tmdb.basic(r.media_type, r.tmdb_id)
                    except ServiceError:
                        return
                    if b:
                        r.poster = r.poster or b.get("poster")
                        r.title = r.title or b.get("title")
                        r.year = r.year or b.get("year")

            await asyncio.gather(*(fill(r) for r in missing))
            ctx.db.commit()

        pushed = None
        if ctx.settings.auto_sync:
            pushed = await _two_way(ctx, collected, rows, prev_watchlist)
            ctx.db.commit()

        _last_pull[_uid(ctx)] = {"at": started, "sources": summary, "titles": len(rows), "pushed": pushed}
        log.info("Synchronisation (compte %s) : %s", _uid(ctx), summary)
        return dict(_last_pull[_uid(ctx)])


# --- Actions ------------------------------------------------------------------------


async def _plex_library_key(ctx: Ctx, media_type: str, tmdb_id: int) -> str | None:
    if not ctx.plex_own:
        return None
    try:
        hit = (await ctx.plex_own.index()).get((media_type, tmdb_id))
    except ServiceError:
        return None
    return hit.get("rating_key") if hit else None


async def act(ctx: Ctx, action: str, media_type: str, tmdb_id: int, rating10: int | None = None, title: str = "") -> dict:
    """action : watchlist_add | watchlist_remove | watched | unwatched | rate | like | unlike | dislike | undislike.
    Renvoie {"services": {nom: "ok" | message d'erreur}, "state": {...}}."""
    tasks: dict[str, asyncio.Future] = {}
    lib_key = await _plex_library_key(ctx, media_type, tmdb_id) if action in ("watched", "unwatched", "rate") else None

    if action == "watchlist_add":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.add_to_watchlist(media_type, tmdb_id)
        if ctx.plex_account:
            tasks["plex"] = ctx.plex_account.add_to_watchlist(media_type, tmdb_id)
    elif action == "watchlist_remove":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.remove_from_watchlist(media_type, tmdb_id)
        if ctx.plex_account:
            tasks["plex"] = ctx.plex_account.remove_from_watchlist(media_type, tmdb_id)
    elif action == "watched":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.add_to_history(media_type, tmdb_id)
        if lib_key:
            tasks["plex"] = ctx.plex_own.scrobble(lib_key)
        elif ctx.plex_account:
            tasks["plex"] = ctx.plex_account.mark_watched(media_type, tmdb_id)
    elif action == "rate":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.rate(media_type, tmdb_id, rating10)
        if lib_key:
            tasks["plex"] = ctx.plex_own.rate(lib_key, rating10)
        elif ctx.plex_account:
            tasks["plex"] = ctx.plex_account.rate(media_type, tmdb_id, rating10)
    elif action == "unwatched":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.remove_from_history(media_type, tmdb_id)
        if lib_key:
            tasks["plex"] = ctx.plex_own.unscrobble(lib_key)
        elif ctx.plex_account:
            tasks["plex"] = ctx.plex_account.mark_unwatched(media_type, tmdb_id)
    elif action == "like":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.add_to_favorites(media_type, tmdb_id)
    elif action == "unlike":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.remove_from_favorites(media_type, tmdb_id)
    elif action == "dislike":
        if ctx.trakt:  # masqué des recommandations Trakt
            tasks["trakt"] = ctx.trakt.hide_recommendation(media_type, tmdb_id)
    elif action == "undislike":
        if ctx.trakt:
            tasks["trakt"] = ctx.trakt.unhide_recommendation(media_type, tmdb_id)
    else:
        raise ValueError(action)

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    services = {}
    for name, res in zip(tasks, results):
        if isinstance(res, ServiceError):
            services[name] = res.message
        elif isinstance(res, Exception):
            log.exception("Action %s sur %s", action, name, exc_info=res)
            services[name] = f"Erreur inattendue : {res.__class__.__name__}"
        elif isinstance(res, dict) and any((res.get("not_found") or {}).get(k) for k in ("movies", "shows", "episodes")):
            services[name] = "Titre introuvable sur Trakt"
        else:
            services[name] = "ok"
    ok = [n for n, v in services.items() if v == "ok"]

    # Sauvegarde locale, toujours
    row = get_row(ctx.db, media_type, tmdb_id, title=title)
    if action == "watchlist_add":
        row.set_sources("watchlist", row.sources("watchlist") | set(ok) | {"local"})
        row.listed_at = row.listed_at or now_iso()
    elif action == "watchlist_remove":
        failed = {n for n, v in services.items() if v != "ok"}
        row.set_sources("watchlist", row.sources("watchlist") & failed)
    elif action == "watched":
        row.set_sources("watched", row.sources("watched") | set(ok) | {"local"})
        row.watched_at = now_iso()
    elif action == "rate":
        row.rating, row.rating_source = rating10, (ok[0] if ok else "local")
    elif action == "unwatched":
        failed = {n for n, v in services.items() if v != "ok"}
        row.set_sources("watched", row.sources("watched") & failed)
        if not row.watched:
            row.watched_at = None
    elif action == "like":
        row.liked = True
    elif action == "unlike":
        row.liked = False
    elif action == "dislike":
        row.disliked, row.liked = True, False
    elif action == "undislike":
        row.disliked = False
    ctx.db.commit()
    return {"services": services, "state": row.state()}


def _plex_episode_history(ctx: Ctx, show_ids: set[int]) -> dict[int, list[dict]]:
    """{tmdb série: [{"number": saison, "episodes": [{"number": n, "watched_at": iso}, …]}]} depuis l'historique Plex."""
    from collections import defaultdict

    from app.models import WatchEvent
    from app.services.history import OWNER_ACCOUNT

    if not show_ids:
        return {}
    rows = ctx.db.execute(
        select(WatchEvent).where(
            WatchEvent.source == "plex", WatchEvent.kind == "episode", WatchEvent.tmdb_id.in_(show_ids),
            WatchEvent.plex_account_id == OWNER_ACCOUNT, WatchEvent.season.isnot(None), WatchEvent.episode.isnot(None),
        )
    ).scalars()
    tree: dict = defaultdict(lambda: defaultdict(list))
    for ev in rows:
        tree[ev.tmdb_id][ev.season].append({"number": ev.episode, "watched_at": ev.watched_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")})
    return {sid: [{"number": n, "episodes": eps} for n, eps in sorted(seasons.items())] for sid, seasons in tree.items()}


# --- Synchronisation bidirectionnelle -------------------------------------------------

# Écritures déjà échouées (titre introuvable…), par compte : pas de nouvel essai en boucle
_failed_once: dict[int, set[tuple]] = defaultdict(set)


async def _two_way(ctx: Ctx, collected: dict, rows: dict, prev_watchlist: dict, dry_run: bool = False) -> dict:
    """Rend Trakt et Plex identiques : watchlist (ajouts ET retraits), vus et notes (ajouts).
    Letterboxd (lecture seule) alimente aussi les vus et notes envoyés aux deux autres."""
    failed = _failed_once[_uid(ctx)]
    ok = {s for s, d in collected.items() if "error" not in d}
    targets = [s for s in ("trakt", "plex") if s in ok and (s != "plex" or ctx.plex_account)]
    report = {"added": {}, "removed": {}, "watched": {}, "ratings": {}, "warnings": []}
    if not targets:
        return report

    wl = {s: set(collected[s].get("watchlist") or {}) for s in targets}

    # --- Watchlist : ajouts et retraits --------------------------------------------
    to_add = {s: [] for s in targets}
    to_remove = {s: [] for s in targets}
    all_keys = set().union(*wl.values()) | {k for k, r in rows.items() if "local" in r.sources("watchlist")}
    for k in all_keys:
        have = {s for s in targets if k in wl[s]}
        prev = prev_watchlist.get(k, set())
        removed_somewhere = {s for s in targets if s in prev and s not in have}
        if removed_somewhere and have:
            # Retiré d'un service depuis la dernière synchro -> on le retire partout
            for s in have:
                to_remove[s].append(k)
        elif not removed_somewhere:
            for s in set(targets) - have:
                if (k, s, True) not in failed:
                    to_add[s].append(k)

    # Garde-fou : un service qui « perd » d'un coup beaucoup de titres est sans doute une erreur de lecture
    for s in targets:
        if len(to_remove[s]) > max(10, len(wl[s]) // 5):
            report["warnings"].append(f"Retraits {s} ignorés par sécurité ({len(to_remove[s])} titres) — vérifie la watchlist puis resynchronise")
            to_remove[s] = []

    # Limite de la watchlist Trakt (compte gratuit)
    if "trakt" in targets and to_add["trakt"]:
        limit = await ctx.trakt.watchlist_limit()
        if limit:
            room = max(0, limit - (len(wl["trakt"]) - len(to_remove["trakt"])))
            if len(to_add["trakt"]) > room:
                # On garde les plus récents
                to_add["trakt"].sort(key=lambda k: rows[k].listed_at or "", reverse=True)
                skipped = len(to_add["trakt"]) - room
                to_add["trakt"] = to_add["trakt"][:room]
                report["warnings"].append(f"Watchlist Trakt limitée à {limit} titres par ton compte : {skipped} titre(s) non copiés sur Trakt")

    if dry_run:
        def titles(keys):
            return [rows[k].title for k in keys if k in rows and rows[k].title][:5]

        watched = {s: set(d.get("watched") or {}) for s, d in collected.items() if "error" not in d}
        ratings = {s: set(d.get("ratings") or {}) for s, d in collected.items() if "error" not in d}
        any_watched = set().union(*watched.values()) if watched else set()
        any_rated = set().union(*ratings.values()) if ratings else set()
        plan = {"warnings": report["warnings"]}
        for s in targets:
            w_missing = [k for k in any_watched - watched.get(s, set()) if s == "trakt" or k[0] == "movie"]
            r_missing = list(any_rated - ratings.get(s, set()))
            plan[s] = {
                "watchlist_add": len(to_add[s]), "watchlist_add_examples": titles(to_add[s]),
                "watchlist_remove": len(to_remove[s]), "watchlist_remove_examples": titles(to_remove[s]),
                "watched_add": len(w_missing), "ratings_add": len(r_missing),
            }
        return plan

    async def run(name: str, coro, on_ok):
        try:
            res = await coro
            on_ok(res)
        except ServiceError as e:
            report["warnings"].append(f"{name} : {e.message}")

    def mark(field: str, keys, source: str, add: bool = True):
        for k in keys:
            if k in rows:
                (rows[k].add_source if add else rows[k].remove_source)(field, source)

    jobs = []
    if "trakt" in targets:
        # Pas de marquage « présumé » : l'état réel est relu à la synchro suivante. Marquer un titre
        # que Trakt a refusé (introuvable) le ferait passer pour « retiré » et le supprimerait de Plex.
        def on_trakt_add(r):
            nf = set(r.get("not_found") or [])
            for k in nf:
                failed.add((k, "trakt", True))
            report["added"]["trakt"] = len(to_add["trakt"]) - len(nf)

        if to_add["trakt"]:
            jobs.append(run("Ajout Trakt", ctx.trakt.add_many("/sync/watchlist", to_add["trakt"]), on_trakt_add))
        if to_remove["trakt"]:
            jobs.append(run("Retrait Trakt", ctx.trakt.add_many("/sync/watchlist/remove", to_remove["trakt"], field="deleted"),
                            lambda r: report["removed"].__setitem__("trakt", len(to_remove["trakt"]))))
    if "plex" in targets:
        async def plex_batch(keys, add: bool):
            done = []
            sem = asyncio.Semaphore(4)

            async def one(k):
                if (k, "plex", add) in failed:
                    return
                async with sem:
                    try:
                        await (ctx.plex_account.add_to_watchlist if add else ctx.plex_account.remove_from_watchlist)(*k)
                        done.append(k)
                    except ServiceError:
                        failed.add((k, "plex", add))

            await asyncio.gather(*(one(k) for k in keys))
            report["added" if add else "removed"]["plex"] = len(done)

        if to_add["plex"]:
            jobs.append(plex_batch(to_add["plex"], True))
        if to_remove["plex"]:
            jobs.append(plex_batch(to_remove["plex"], False))
    await asyncio.gather(*jobs)

    # Les retraits propagés : plus de trace « local » non plus
    for s in targets:
        for k in to_remove[s]:
            if k in rows:
                rows[k].remove_source("watchlist", "local")

    # --- Vus et notes : ajouts uniquement ------------------------------------------------
    watched = {s: set(d.get("watched") or {}) for s, d in collected.items() if "error" not in d}
    ratings = {s: dict(d.get("ratings") or {}) for s, d in collected.items() if "error" not in d}
    any_watched = set().union(*watched.values()) if watched else set()
    lib_index = await ctx.plex_own.index() if ctx.plex_own else {}

    if "trakt" in targets:
        dates = {}
        for src in ("plex", "letterboxd"):
            for k, when in (collected.get(src, {}).get("watched") or {}).items():
                if when and k not in dates:
                    dates[k] = when if "T" in when else f"{when}T20:00:00.000Z"
        missing = [k for k in any_watched if k not in watched.get("trakt", set()) and (k, "trakt", "watched") not in failed]
        if missing:
            episodes = _plex_episode_history(ctx, {k[1] for k in missing if k[0] == "tv"})
            entries = []
            for k in missing:
                if k[0] == "tv" and episodes.get(k[1]):
                    entries.append((k[0], k[1], {"seasons": episodes[k[1]]}))  # chaque épisode à sa vraie date
                else:
                    # Sans date connue : date de sortie (jamais l'heure de l'envoi, qui fausserait l'historique)
                    entries.append((k[0], k[1], {"watched_at": dates.get(k, "released")}))

            def on_watched(r):
                nf = set(r.get("not_found") or [])
                for k in nf:
                    failed.add((k, "trakt", "watched"))  # inconnu de Trakt : on ne renvoie plus
                ok_keys = [k for k in missing if k not in nf]
                report["watched"]["trakt"] = len(ok_keys)
                mark("watched", ok_keys, "trakt")

            await run("Vus → Trakt", ctx.trakt.add_many("/sync/history", entries), on_watched)
        rate_missing = []
        for k in set().union(*[set(r) for r in ratings.values()]) - set(ratings.get("trakt", {})):
            for src in ("plex", "letterboxd"):
                if k in ratings.get(src, {}):
                    rate_missing.append((k[0], k[1], ratings[src][k]))
                    break
        if rate_missing:
            await run("Notes → Trakt", ctx.trakt.add_many("/sync/ratings", rate_missing),
                      lambda r: report["ratings"].__setitem__("trakt", len(rate_missing)))

    if "plex" in targets:
        plex_seen = watched.get("plex", set())
        sem = asyncio.Semaphore(4)
        counts = {"watched": 0, "ratings": 0}

        async def plex_write(kind: str, k, value=None):
            if (k, "plex", kind) in failed:
                return
            async with sem:
                try:
                    hit = lib_index.get(k)
                    if kind == "watched":
                        await (ctx.plex_own.scrobble(hit["rating_key"]) if hit else ctx.plex_account.mark_watched(*k))
                        mark("watched", [k], "plex")
                    else:
                        await (ctx.plex_own.rate(hit["rating_key"], value) if hit else ctx.plex_account.rate(k[0], k[1], value))
                    counts[kind] += 1
                except ServiceError:
                    failed.add((k, "plex", kind))

        tasks = [plex_write("watched", k) for k in any_watched - plex_seen if k[0] == "movie"]
        for k in set().union(*[set(r) for r in ratings.values()]) - set(ratings.get("plex", {})):
            for src in ("trakt", "letterboxd"):
                if k in ratings.get(src, {}):
                    tasks.append(plex_write("ratings", k, ratings[src][k]))
                    break
        await asyncio.gather(*tasks)
        report["watched"]["plex"] = counts["watched"]
        report["ratings"]["plex"] = counts["ratings"]

    log.info("Synchro bidirectionnelle : %s", report)
    return report
