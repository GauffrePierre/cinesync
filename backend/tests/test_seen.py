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


# --- Sorties récentes de la watchlist --------------------------------------------------------


class FakeReleases:
    is_mock = False

    def __init__(self, today):
        from datetime import timedelta

        ago = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731
        self.dates = {
            10: {"cinema": [ago(5)], "streaming": []},  # sorti en salles il y a 5 jours
            11: {"cinema": [ago(200)], "streaming": [ago(2)]},  # arrivé en VOD il y a 2 jours
            12: {"cinema": [ago(90)], "streaming": []},  # trop ancien
            13: {"cinema": [], "streaming": []},  # pas de date pour le pays : date mondiale
            14: {"cinema": [ago(3000), ago(3)], "streaming": []},  # ressortie en salles
        }
        self.world = {13: ago(10)}
        self.shows = {
            20: {"last_episode_to_air": {"air_date": ago(1), "season_number": 3, "episode_number": 1}},
            21: {"last_episode_to_air": {"air_date": ago(60), "season_number": 1, "episode_number": 8}},
        }

    async def release_dates(self, tmdb_id):
        return self.dates[tmdb_id]

    async def _get(self, path, ttl=0, **params):
        return self.shows[int(path.rsplit("/", 1)[1])]

    async def basic(self, media_type, tmdb_id):
        return {"id": tmdb_id, "media_type": media_type, "title": f"T{tmdb_id}", "release_date": self.world.get(tmdb_id)}


def test_watchlist_releases(db):
    from datetime import date

    rows = [MediaState(tmdb_id=i, media_type="movie", watchlist_sources='["local"]') for i in (10, 11, 12, 13, 14)]
    rows += [MediaState(tmdb_id=i, media_type="tv", watchlist_sources='["trakt"]') for i in (20, 21)]
    rows.append(MediaState(tmdb_id=99, media_type="movie", watchlist_sources='["local"]', watched_sources='["local"]'))  # déjà vu
    db.add_all(rows)
    db.commit()
    ctx = SimpleNamespace(db=db, user=db.get(User, 1), tmdb=FakeReleases(date.today()))
    out = asyncio.run(suggestions.watchlist_releases(ctx, 30))
    assert [(i["id"], i["reason"]) for i in out] == [
        (20, "Nouvelle saison"), (11, "Sorti en VOD / streaming"), (14, "Ressortie au cinéma"), (10, "Sorti au cinéma"),
        (13, "Sorti au cinéma"),
    ]
    assert asyncio.run(suggestions.watchlist_releases(ctx, 0)) == []


def test_watchlist_seen_filter(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    for tid, title in ((603, "Matrix"), (604, "Matrix Reloaded")):
        admin.post("/api/library/watchlist", json={"tmdb_id": tid, "media_type": "movie", "title": title})
    admin.post("/api/library/watched", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"})
    ids = lambda seen: [i["id"] for i in admin.get(f"/api/library/watchlist?seen={seen}").json()["results"]]  # noqa: E731
    assert sorted(ids("all")) == [603, 604]
    assert ids("seen") == [603] and ids("unseen") == [604]
