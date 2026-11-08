"""Réglage « ne plus proposer les titres déjà vus » : films vus, séries vues et à jour."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

from app.models import MediaState, User, WatchEvent
from app.services import suggestions
from app.services.suggestions import _caught_up
from tests.test_accounts import client, fresh, setup_admin  # noqa: F401 (fixture)

AIRED_S2E8 = {"last_episode_to_air": {"air_date": "2026-10-01", "season_number": 2, "episode_number": 8}, "status": "Returning Series"}


def test_caught_up_from_episode_history():
    assert _caught_up(AIRED_S2E8, (2, 8), None)
    assert not _caught_up(AIRED_S2E8, (2, 7), "2026-11-01")  # l'historique prime sur la date
    assert not _caught_up(AIRED_S2E8, (1, 10), None)


def test_caught_up_from_dates_or_status():
    assert _caught_up(AIRED_S2E8, None, "2026-10-02T20:00:00")
    assert not _caught_up(AIRED_S2E8, None, "2026-09-30T20:00:00")
    assert not _caught_up(AIRED_S2E8, None, None)  # série en cours, aucune date : reste proposée
    assert _caught_up({**AIRED_S2E8, "status": "Ended"}, None, None)
    assert _caught_up({"last_episode_to_air": None}, None, None)


class FakeTMDB:
    is_mock = False

    def __init__(self, shows):
        self.shows = shows
        self.calls = 0

    async def _get(self, path, ttl=0, **params):
        self.calls += 1
        return self.shows[int(path.rsplit("/", 1)[1])]


def test_seen_keys(db):
    db.add_all(
        [
            MediaState(tmdb_id=603, media_type="movie", watched_sources='["trakt"]'),
            MediaState(tmdb_id=604, media_type="movie", watchlist_sources='["local"]'),  # pas vu
            MediaState(tmdb_id=1, media_type="tv", watched_sources='["trakt"]'),  # à jour (historique)
            MediaState(tmdb_id=2, media_type="tv", watched_sources='["trakt"]'),  # nouvel épisode depuis
            WatchEvent(source="trakt", source_key="a", kind="episode", tmdb_id=1, season=2, episode=8, watched_at=datetime(2026, 10, 2)),
            WatchEvent(source="trakt", source_key="b", kind="episode", tmdb_id=2, season=2, episode=7, watched_at=datetime(2026, 9, 25)),
            WatchEvent(source="plex", source_key="c", kind="episode", tmdb_id=3, season=1, episode=6, watched_at=datetime(2026, 5, 1)),  # vue sur Plex seulement
        ]
    )
    db.commit()
    ended = {"last_episode_to_air": {"air_date": "2020-01-01", "season_number": 1, "episode_number": 6}, "status": "Ended"}
    tmdb = FakeTMDB({1: AIRED_S2E8, 2: AIRED_S2E8, 3: ended})
    ctx = SimpleNamespace(db=db, user=db.get(User, 1), tmdb=tmdb)
    keys = asyncio.run(suggestions.seen_keys(ctx))
    assert keys == {("movie", 603), ("tv", 1), ("tv", 3)}
    # Mis en cache tant que rien ne change…
    asyncio.run(suggestions.seen_keys(ctx))
    assert tmdb.calls == 3
    # …et recalculé dès qu'un épisode est vu
    db.add(WatchEvent(source="trakt", source_key="d", kind="episode", tmdb_id=2, season=2, episode=8, watched_at=datetime(2026, 10, 3)))
    db.commit()
    assert ("tv", 2) in asyncio.run(suggestions.seen_keys(ctx))


def test_setting_and_endpoint(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    assert admin.get("/api/settings").json()["hide_seen"] is False
    assert admin.put("/api/settings", json={"hide_seen": True}).json()["hide_seen"] is True
    assert admin.post("/api/library/watched", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}).status_code == 200
    assert admin.get("/api/library/seen").json() == {"keys": ["movie:603"]}
