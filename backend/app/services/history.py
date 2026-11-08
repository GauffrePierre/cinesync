"""Historique des visionnages : import incrémental (Plex, Trakt, Letterboxd) et statistiques.

Import :
- Plex : /status/sessions/history/all du serveur (le plus complet, avec le compte qui a regardé).
- Trakt : /sync/history (extended=full, avec durées).
- Letterboxd : journal RSS (films, à la journée).
Un visionnage déjà connu par une autre source (même titre, à quelques heures près) n'est pas réimporté.
"""

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select

from app.models import MediaState, WatchEvent
from app.services.context import Ctx
from app.services.errors import ServiceError
from app.services.http import http

log = logging.getLogger(__name__)

OWNER_ACCOUNT = 1  # sur un serveur Plex, le propriétaire a toujours l'accountID 1
DUP_WINDOW = timedelta(hours=12)
BULK_PER_MINUTE = 20  # au-delà, des entrées Trakt à la même minute sont un import en masse, pas des visionnages réels


def _show_key(m: dict) -> str | None:
    """Identifiant Plex de la série d'un épisode (l'historique donne grandparentKey, pas grandparentRatingKey)."""
    return m.get("grandparentRatingKey") or ((m.get("grandparentKey") or "").rsplit("/", 1)[-1] or None)


def _utc(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)


def _parse_iso(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _known_title(db, kind, tmdb, s, e) -> bool:
    """Ce film / cet épisode a-t-il déjà un visionnage (n'importe quand) ? Évite de compter deux fois un import en masse."""
    if not tmdb:
        return False
    q = select(WatchEvent.id).where(WatchEvent.kind == kind, WatchEvent.tmdb_id == tmdb, WatchEvent.season.is_(s) if s is None else WatchEvent.season == s,
                                    WatchEvent.episode.is_(e) if e is None else WatchEvent.episode == e).limit(1)
    return db.execute(q).first() is not None


class _Dedup:
    """Index des visionnages existants : (kind, tmdb, saison, épisode) -> dates."""

    def __init__(self, db):
        self.idx: dict[tuple, list[datetime]] = defaultdict(list)
        for kind, tmdb, s, e, at in db.execute(select(WatchEvent.kind, WatchEvent.tmdb_id, WatchEvent.season, WatchEvent.episode, WatchEvent.watched_at)):
            if tmdb:
                self.idx[(kind, tmdb, s, e)].append(at)

    def seen(self, kind, tmdb, s, e, at: datetime, window=DUP_WINDOW) -> bool:
        return bool(tmdb) and any(abs(at - x) <= window for x in self.idx.get((kind, tmdb, s, e), []))

    def add(self, kind, tmdb, s, e, at):
        if tmdb:
            self.idx[(kind, tmdb, s, e)].append(at)


# --- Import Plex -------------------------------------------------------------------------


async def _plex_get(ctx: Ctx, path: str, client=None, **params) -> dict:
    p = client or ctx.plex
    try:
        r = await http().get(p.url + path, params=params, headers={"X-Plex-Token": p.token, "Accept": "application/json"}, timeout=60.0)
    except httpx.HTTPError as e:
        raise ServiceError("plex", f"Serveur Plex injoignable : {e.__class__.__name__}") from e
    if r.status_code >= 400:
        raise ServiceError("plex", f"Historique Plex indisponible ({r.status_code})")
    return r.json().get("MediaContainer", {})


def plex_account_map(db) -> dict[int, int]:
    """Compte de l'historique du serveur Plex (accountID) -> compte SynCiné."""
    from app.models import User

    out = {OWNER_ACCOUNT: 1}  # par défaut, le propriétaire du serveur est l'administrateur principal
    for u in db.query(User).filter(User.plex_server_account_id.isnot(None)).all():
        out[u.plex_server_account_id] = u.id
    return out


def assign_plex_events(db, server_account_id: int, user_id: int) -> None:
    """Rattache à un compte SynCiné les visionnages Plex déjà importés de son compte Plex."""
    from sqlalchemy import update

    db.execute(
        update(WatchEvent)
        .where(WatchEvent.source == "plex", WatchEvent.plex_account_id == server_account_id)
        .values(user_id=user_id)
        .execution_options(all_users=True, synchronize_session=False)
    )
    db.commit()


async def import_plex(ctx: Ctx) -> int:
    """Historique de tout le serveur (jeton de l'admin) ; chaque visionnage revient au compte qui a regardé
    (0 = compte Plex sans compte SynCiné, rattaché plus tard si l'admin l'autorise)."""
    p = ctx.plex_admin
    if not p:
        return 0
    db = ctx.db
    last = db.execute(select(func.max(WatchEvent.watched_at)).where(WatchEvent.source == "plex").execution_options(all_users=True)).scalar()
    lib = await p.library()
    accounts = plex_account_map(db)
    by_key = {i["rating_key"]: i for i in lib}

    # Pages du plus récent au plus ancien, jusqu'à retrouver ce qui est déjà importé
    raw, start = [], 0
    while True:
        mc = await _plex_get(ctx, "/status/sessions/history/all", client=p, sort="viewedAt:desc", **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": 500})
        items = mc.get("Metadata", []) or []
        stop = False
        for m in items:
            at = _utc(m["viewedAt"]) if m.get("viewedAt") else None
            if at is None:
                continue
            if last and at <= last:
                stop = True
                break
            raw.append((m, at))
        start += len(items)
        if stop or not items or start >= (mc.get("totalSize") or 0):
            break

    # Durées des épisodes : une requête par série concernée
    durations: dict[str, int] = {}
    shows = {_show_key(m) for m, _ in raw if m.get("type") == "episode" and _show_key(m)}
    sem = asyncio.Semaphore(6)

    async def leaves(show_key: str):
        async with sem:
            try:
                mc = await _plex_get(ctx, f"/library/metadata/{show_key}/allLeaves", client=p)
            except ServiceError:
                return
            for e in mc.get("Metadata", []) or []:
                if e.get("duration"):
                    durations[e["ratingKey"]] = round(e["duration"] / 60000)

    await asyncio.gather(*(leaves(k) for k in shows))

    dedup = _Dedup(db)
    added = 0
    for m, at in raw:
        typ = m.get("type")
        if typ == "movie":
            lib_item = by_key.get(m.get("ratingKey")) or {}
            kind, tmdb, season, episode = "movie", lib_item.get("id"), None, None
            runtime = lib_item.get("duration_min")
            show_title = ""
        elif typ == "episode":
            show = by_key.get(_show_key(m)) or {}
            kind, tmdb, season, episode = "episode", show.get("id"), m.get("parentIndex"), m.get("index")
            runtime = durations.get(m.get("ratingKey"))
            show_title = m.get("grandparentTitle") or show.get("title") or ""
        else:
            continue
        key = f"{m.get('ratingKey')}:{m.get('viewedAt')}:{m.get('accountID')}"
        db.add(
            WatchEvent(
                user_id=accounts.get(m.get("accountID"), 0),
                source="plex", source_key=key, plex_account_id=m.get("accountID"), kind=kind, tmdb_id=tmdb,
                title=m.get("title") or "", show_title=show_title, season=season, episode=episode, watched_at=at, runtime_min=runtime,
            )
        )
        dedup.add(kind, tmdb, season, episode, at)
        added += 1
    db.commit()
    return added


# --- Import Trakt / Letterboxd -----------------------------------------------------------


async def import_trakt(ctx: Ctx) -> int:
    if not ctx.trakt:
        return 0
    db = ctx.db
    last = db.execute(select(func.max(WatchEvent.watched_at)).where(WatchEvent.source == "trakt")).scalar()
    dedup = _Dedup(db)
    known = set(db.execute(select(WatchEvent.source_key).where(WatchEvent.source == "trakt")).scalars())
    params = {"extended": "full"}
    if last:
        params["start_at"] = (last - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    history = await ctx.trakt._get_all("/sync/history", params)
    # Imports en masse (dizaines d'entrées à la même minute) : la date n'est pas celle du visionnage
    per_minute = Counter((h.get("watched_at") or "")[:16] for h in history)
    bulk = {m for m, n in per_minute.items() if n >= BULK_PER_MINUTE}
    added = 0
    for h in history:
        approx = (h.get("watched_at") or "")[:16] in bulk
        key = str(h.get("id"))
        at = _parse_iso(h.get("watched_at") or "")
        if key in known or at is None:
            continue
        if h.get("type") == "movie":
            mv = h.get("movie", {})
            kind, tmdb, s, e = "movie", mv.get("ids", {}).get("tmdb"), None, None
            title, show_title, runtime = mv.get("title") or "", "", mv.get("runtime")
        elif h.get("type") == "episode":
            ep, sh = h.get("episode", {}), h.get("show", {})
            kind, tmdb, s, e = "episode", sh.get("ids", {}).get("tmdb"), ep.get("season"), ep.get("number")
            title, show_title, runtime = ep.get("title") or "", sh.get("title") or "", ep.get("runtime")
        else:
            continue
        known.add(key)
        if dedup.seen(kind, tmdb, s, e, at) or (approx and _known_title(db, kind, tmdb, s, e)):
            continue  # déjà connu par Plex (ex. recopié par la synchro)
        db.add(WatchEvent(source="trakt", source_key=key, kind=kind, tmdb_id=tmdb, title=title, show_title=show_title, season=s, episode=e, watched_at=at, runtime_min=runtime, approx_date=approx))
        dedup.add(kind, tmdb, s, e, at)
        added += 1
    # Imports en masse déjà enregistrés : date marquée approximative
    stored = Counter(at.strftime("%Y-%m-%dT%H:%M") for (at,) in db.execute(select(WatchEvent.watched_at).where(WatchEvent.source == "trakt")))
    for minute, n in stored.items():
        if n >= BULK_PER_MINUTE:
            start = datetime.strptime(minute, "%Y-%m-%dT%H:%M")
            for ev in db.execute(select(WatchEvent).where(WatchEvent.source == "trakt", WatchEvent.watched_at >= start, WatchEvent.watched_at < start + timedelta(minutes=1))).scalars():
                ev.approx_date = True
    db.commit()
    return added


async def import_letterboxd(ctx: Ctx) -> int:
    if not ctx.letterboxd:
        return 0
    db = ctx.db
    dedup = _Dedup(db)
    known = set(db.execute(select(WatchEvent.source_key).where(WatchEvent.source == "letterboxd")).scalars())
    added = 0
    for d in await ctx.letterboxd.diary():
        if not d.get("tmdb_id") or not d.get("watched_date"):
            continue
        key = f"{d['tmdb_id']}:{d['watched_date']}"
        at = _parse_iso(d["watched_date"] + "T20:00:00")
        if key in known or at is None or dedup.seen("movie", d["tmdb_id"], None, None, at, timedelta(days=1)):
            continue
        db.add(WatchEvent(source="letterboxd", source_key=key, kind="movie", tmdb_id=d["tmdb_id"], title=d.get("title") or "", watched_at=at))
        added += 1
    db.commit()
    return added


async def enrich_events(ctx: Ctx, limit: int = 300) -> None:
    """Genres et durées manquantes, via TMDB (par titre, une fois)."""
    if ctx.tmdb.is_mock:
        return
    db = ctx.db
    todo = db.execute(select(WatchEvent).where(WatchEvent.tmdb_id.isnot(None), WatchEvent.genres == "[]")).scalars().all()
    titles = {}
    for ev in todo:
        titles.setdefault(("movie" if ev.kind == "movie" else "tv", ev.tmdb_id), []).append(ev)
    genre_names = {}
    for mt in ("movie", "tv"):
        try:
            genre_names.update(await ctx.tmdb.genres(mt))
        except ServiceError:
            pass
    sem = asyncio.Semaphore(8)

    async def one(k, evs):
        async with sem:
            try:
                raw = await ctx.tmdb._get(f"/{k[0]}/{k[1]}", ttl=604800)
            except ServiceError:
                return
        names = [g["name"] for g in raw.get("genres", [])] or ["Autre"]
        runtime = raw.get("runtime") if k[0] == "movie" else ((raw.get("episode_run_time") or [None])[0])
        for ev in evs:
            ev.genres = json.dumps(names)
            if not ev.runtime_min and runtime:
                ev.runtime_min = runtime

    await asyncio.gather(*(one(k, evs) for k, evs in list(titles.items())[:limit]))
    db.commit()


_import_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_plex_lock = asyncio.Lock()


async def import_all(ctx: Ctx) -> dict:
    async with _import_locks[ctx.user.id]:
        return await _import_all(ctx)


async def _import_plex_once(ctx: Ctx) -> int:
    async with _plex_lock:
        return await import_plex(ctx)


async def _import_all(ctx: Ctx) -> dict:
    out = {}
    # L'historique Plex couvre tout le serveur : importé une fois (par l'admin) pour tous les comptes
    sources = (("plex", _import_plex_once),) if ctx.user.is_admin else ()
    for name, fn in sources + (("trakt", import_trakt), ("letterboxd", import_letterboxd)):
        try:
            out[name] = await fn(ctx)
        except ServiceError as e:
            out[name] = e.message
    try:
        await enrich_events(ctx)
    except ServiceError:
        pass
    return out


# --- Statistiques ------------------------------------------------------------------------

PERIODS = {"day": 30, "week": 12, "month": 12, "year": None}


def _bucket_start(d: datetime, period: str) -> datetime:
    d = d.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return d - timedelta(days=d.weekday())
    if period == "month":
        return d.replace(day=1)
    if period == "year":
        return d.replace(month=1, day=1)
    return d


def _shift(d: datetime, period: str, n: int) -> datetime:
    if period == "day":
        return d + timedelta(days=n)
    if period == "week":
        return d + timedelta(weeks=n)
    if period == "month":
        m = d.month - 1 + n
        return d.replace(year=d.year + m // 12, month=m % 12 + 1)
    return d.replace(year=d.year + n)


def _mine(q, account: int | None):
    """Visionnages de l'utilisateur : ceux de son compte Plex + Trakt / Letterboxd (personnels)."""
    if account is None:
        return q
    return q.where((WatchEvent.source != "plex") | (WatchEvent.plex_account_id == account))


def stats(db, period: str = "week", offset: int = 0, account: int | None = None, tz_offset_min: int = 0) -> dict:
    """Statistiques sur une fenêtre de N périodes (day=30 jours, week=12 semaines, month=12 mois, year=tout).
    offset : décalage de la fenêtre vers le passé (0 = jusqu'à aujourd'hui)."""
    tz = timedelta(minutes=tz_offset_min)
    now = datetime.utcnow() + tz
    every = list(db.execute(_mine(select(WatchEvent), account).order_by(WatchEvent.watched_at)).scalars())
    events = [(ev, ev.watched_at + tz) for ev in every if not ev.approx_date]  # datés précisément
    n = PERIODS[period]
    end_bucket = _shift(_bucket_start(now, period), period, -offset * (n or 0))
    if n is None:  # années : de la première à la dernière
        first = events[0][1] if events else now
        starts = []
        y = _bucket_start(first, "year")
        while y <= end_bucket:
            starts.append(y)
            y = _shift(y, "year", 1)
    else:
        starts = [_shift(end_bucket, period, -i) for i in range(n - 1, -1, -1)]
    window_start, window_end = starts[0], _shift(starts[-1], period, 1)

    buckets = {s: {"start": s.date().isoformat(), "movies": 0, "episodes": 0, "minutes": 0} for s in starts}
    in_window = [(ev, local) for ev, local in events if window_start <= local < window_end]
    weekday, hour, genres = [0] * 7, [0] * 24, Counter()
    shows, movies, days = defaultdict(lambda: {"episodes": 0, "minutes": 0, "tmdb_id": None}), Counter(), set()
    for ev, local in in_window:
        b = buckets[_bucket_start(local, period)]
        b["movies" if ev.kind == "movie" else "episodes"] += 1
        b["minutes"] += ev.runtime_min or 0
        weekday[local.weekday()] += 1
        hour[local.hour] += 1
        days.add(local.date())
        for g in json.loads(ev.genres or "[]"):
            genres[g] += 1
        if ev.kind == "episode":
            sh = shows[ev.show_title or "?"]
            sh["episodes"] += 1
            sh["minutes"] += ev.runtime_min or 0
            sh["tmdb_id"] = ev.tmdb_id
        else:
            movies[(ev.title, ev.tmdb_id)] += 1

    # Plus longue série de jours consécutifs (sur tout l'historique)
    all_days = sorted({local.date() for _, local in events})
    best = cur = 0
    for i, d in enumerate(all_days):
        cur = cur + 1 if i and (d - all_days[i - 1]).days == 1 else 1
        best = max(best, cur)

    minutes = sum(b["minutes"] for b in buckets.values())
    ratings = Counter(r for (r,) in db.execute(select(MediaState.rating).where(MediaState.rating.isnot(None))))
    return {
        "period": period,
        "offset": offset,
        "window": {"start": window_start.date().isoformat(), "end": (window_end - timedelta(days=1)).date().isoformat()},
        "buckets": list(buckets.values()),
        "totals": {
            "movies": sum(b["movies"] for b in buckets.values()),
            "episodes": sum(b["episodes"] for b in buckets.values()),
            "hours": round(minutes / 60, 1),
            "active_days": len(days),
            "shows": len(shows),
            "all_time": {
                "events": len(every),
                "hours": round(sum((e.runtime_min or 0) for e in every) / 60),
                "longest_streak": best,
                "undated": len(every) - len(events),
            },
        },
        "weekday": weekday,
        "hour": hour,
        "top_genres": [{"name": g, "count": c} for g, c in genres.most_common(8)],
        "top_shows": sorted(({"title": t, **v} for t, v in shows.items()), key=lambda x: -x["episodes"])[:8],
        "top_movies": [{"title": t, "tmdb_id": i, "count": c} for (t, i), c in movies.most_common(8)],
        "ratings": [{"rating": r, "count": ratings.get(r, 0)} for r in range(1, 11)],
        "has_more_past": bool(events) and events[0][1] < window_start,
    }


def events_between(db, start: str, end: str, account: int | None = None, tz_offset_min: int = 0) -> list[dict]:
    """Détail des visionnages d'une période (clic sur une barre)."""
    tz = timedelta(minutes=tz_offset_min)
    a, b = datetime.fromisoformat(start) - tz, datetime.fromisoformat(end) - tz
    q = _mine(select(WatchEvent).where(WatchEvent.watched_at >= a, WatchEvent.watched_at < b), account).order_by(WatchEvent.watched_at.desc())
    return [
        {
            "kind": ev.kind, "tmdb_id": ev.tmdb_id, "title": ev.title, "show_title": ev.show_title, "season": ev.season,
            "episode": ev.episode, "watched_at": (ev.watched_at + tz).isoformat(), "runtime_min": ev.runtime_min, "source": ev.source,
        }
        for ev in db.execute(q).scalars()
    ]
