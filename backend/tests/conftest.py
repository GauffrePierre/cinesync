"""Configuration des tests : base SQLite temporaire, faux services Trakt / Plex qui enregistrent leurs appels."""

import os
import tempfile

# Avant tout import de l'appli : base de test isolée
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cinesync-test-")

import pytest  # noqa: E402

from app.database import Base, SessionLocal, bind_user, engine, init_db  # noqa: E402
from app.models import User, UserSettings  # noqa: E402
from app.services import library_sync  # noqa: E402
from app.services.cache import cache  # noqa: E402
from app.services.errors import ServiceError  # noqa: E402


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    init_db()
    cache.clear()
    library_sync._failed_once.clear()  # dict par compte
    library_sync._last_pull.clear()
    with SessionLocal() as session:
        bind_user(session, 1)  # comme une requête du compte administrateur
        yield session


class FakeTrakt:
    """Watchlist / vus / notes en mémoire ; add_many enregistre (chemin, références)."""

    def __init__(self, watchlist=(), watched=(), ratings=None, limit=None, fail=False, not_found=()):
        self.wl = list(watchlist)
        self.watched = set(watched)
        self.r = dict(ratings or {})
        self.limit = limit
        self.fail = fail
        self.not_found = list(not_found)
        self.calls = []

    def _check(self):
        if self.fail:
            raise ServiceError("trakt", "Trakt en panne")

    async def watchlist(self):
        self._check()
        return [{"tmdb_id": k[1], "media_type": k[0], "title": f"T{k[1]}", "year": 2020, "listed_at": "2026-01-01T00:00:00Z"} for k in self.wl]

    async def watched_keys(self):
        self._check()
        return set(self.watched)

    async def ratings(self):
        self._check()
        return [{"tmdb_id": k[1], "media_type": k[0], "rating": v, "title": "", "year": None} for k, v in self.r.items()]

    async def watchlist_limit(self):
        return self.limit

    async def add_many(self, path, refs, field="added"):
        self.calls.append((path, list(refs)))
        nf = [(r[0], r[1]) for r in refs if (r[0], r[1]) in self.not_found]
        return {field: len(refs) - len(nf), "not_found": nf}

    async def add_to_watchlist(self, mt, tid):
        self._check()
        self.calls.append(("add", (mt, tid)))

    async def remove_from_watchlist(self, mt, tid):
        self._check()
        self.calls.append(("remove", (mt, tid)))

    async def add_to_history(self, mt, tid):
        self.calls.append(("history", (mt, tid)))

    async def rate(self, mt, tid, r):
        self.calls.append(("rate", (mt, tid, r)))

    async def add_to_favorites(self, mt, tid):
        self.calls.append(("favorite", (mt, tid)))

    async def remove_from_history(self, mt, tid):
        self.calls.append(("unhistory", (mt, tid)))

    async def remove_from_favorites(self, mt, tid):
        self.calls.append(("unfavorite", (mt, tid)))

    async def hide_recommendation(self, mt, tid):
        self.calls.append(("hide", (mt, tid)))

    async def unhide_recommendation(self, mt, tid):
        self.calls.append(("unhide", (mt, tid)))


class FakePlexAccount:
    def __init__(self, watchlist=(), fail_writes=False):
        self.wl = list(watchlist)
        self.fail_writes = fail_writes
        self.calls = []

    async def watchlist(self):
        return [{"tmdb_id": k[1], "media_type": k[0], "title": f"P{k[1]}", "year": 2021, "poster": None, "plex_key": str(k[1])} for k in self.wl]

    async def _write(self, name, *args):
        if self.fail_writes:
            raise ServiceError("plex", "Plex refuse")
        self.calls.append((name, args))

    async def add_to_watchlist(self, mt, tid):
        await self._write("add", mt, tid)

    async def remove_from_watchlist(self, mt, tid):
        await self._write("remove", mt, tid)

    async def mark_watched(self, mt, tid):
        await self._write("watched", mt, tid)

    async def rate(self, mt, tid, r):
        await self._write("rate", mt, tid, r)

    async def mark_unwatched(self, mt, tid):
        await self._write("unwatched", mt, tid)


class FakePlexServer:
    """Bibliothèque du serveur : items normalisés comme PlexClient.library()."""

    def __init__(self, items=()):
        self.items = list(items)
        self.calls = []

    async def library(self):
        return self.items

    async def index(self):
        return {(i["media_type"], i["id"]): i for i in self.items}

    async def scrobble(self, rk):
        self.calls.append(("scrobble", rk))

    async def rate(self, rk, r):
        self.calls.append(("rate", rk, r))


class FakeTMDB:
    is_mock = True  # pas de récupération d'affiches pendant les tests


class FakeCtx:
    def __init__(self, db, trakt=None, plex_account=None, plex=None, auto_sync=True):
        self.db = db
        self.settings = db.get(UserSettings, 1)
        self.settings.auto_sync = auto_sync
        db.commit()
        self.trakt = trakt
        self.plex_account = plex_account
        self.plex = self.plex_own = plex
        self.user = db.get(User, 1)
        self.letterboxd = None
        self.tmdb = FakeTMDB()


def lib_item(mt, tid, rk, **kw):
    base = {"media_type": mt, "id": tid, "rating_key": rk, "title": f"L{tid}", "year": 2019, "view_count": 0,
            "episodes": None, "viewed_episodes": None, "user_rating": None, "last_viewed_at": None}
    return {**base, **kw}
