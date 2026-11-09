"""Quand prévenir : nouveaux épisodes (diffusion, plateformes, serveur Plex / Jellyfin) et titres de la watchlist (plateformes, serveur)."""

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app import scheduler
from app.models import MediaState, Notification, UserSettings
from app.services.clock import utcnow
from tests.test_accounts import client, fresh, setup_admin  # noqa: F401 (fixture)

TODAY = date.today().isoformat()
NETFLIX = {"id": 8, "name": "Netflix", "logo": None}


class FakeTMDB:
    is_mock = False

    def __init__(self, on_netflix=()):
        self.on_netflix = set(on_netflix)

    async def _get(self, path, ttl=0, **params):
        return {"name": "Breaking Bad", "poster_path": None,
                "last_episode_to_air": {"air_date": TODAY, "season_number": 1, "episode_number": 2, "name": ""}}

    async def providers(self, media_type, tmdb_id, fresh=False):
        return {"flatrate": [NETFLIX]} if tmdb_id in self.on_netflix else {}


class FakePlex:
    async def index(self):
        return {("movie", 603): {"id": 603}}

    async def library(self):
        return [{"media_type": "tv", "id": 1396, "rating_key": "77", "title": "Breaking Bad"}]

    async def recent_episodes(self, days=2):
        return [{"show_key": "77", "season": 1, "episode": n, "added_at": 0} for n in (3, 4, 5)]


class FakeJellyfin(FakePlex):
    label = "Jellyfin"

    async def library(self):
        return [{"media_type": "tv", "id": 1396, "rating_key": "jf-show", "title": "Breaking Bad"}]

    async def recent_episodes(self, days=2):
        return [{"show_key": "jf-show", "season": 2, "episode": 1, "added_at": "2026-11-09T08:00:00Z"}]


def _ctx(db, via_ep=None, via_movie=None, platforms=(), tmdb=None, plex=None, jellyfin=None):
    s = db.get(UserSettings, 1)
    s.notify_episode_via = __import__("json").dumps(via_ep or ["air"])
    s.notify_movie_via = __import__("json").dumps(via_movie or ["platforms"])
    db.commit()
    return SimpleNamespace(db=db, settings=s, platforms=list(platforms), tmdb=tmdb or FakeTMDB(), plex=plex, media=plex or jellyfin)


def _messages(db):
    return sorted(n.message for n in db.query(Notification).all())


def test_settings_round_trip(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    s = admin.get("/api/settings").json()
    assert s["notify_episode_via"] == ["air"] and s["notify_movie_via"] == ["platforms"]
    s = admin.put("/api/settings", json={"notify_episode_via": ["plex", "platforms"], "notify_movie_via": ["plex"]}).json()
    assert s["notify_episode_via"] == ["platforms", "plex"] and s["notify_movie_via"] == ["plex"]
    assert admin.put("/api/settings", json={"notify_episode_via": ["sms"]}).status_code == 422


def test_episode_triggers(db, monkeypatch):
    monkeypatch.setattr(scheduler, "stream_providers", lambda p: p.get("flatrate", []))
    db.add(MediaState(tmdb_id=1396, media_type="tv", watchlist_sources='["local"]'))
    db.commit()
    # Seulement « sur mes plateformes » : rien tant que la série n'y est pas
    asyncio.run(scheduler.episodes_one(_ctx(db, ["platforms"], platforms=[8])))
    assert _messages(db) == []
    asyncio.run(scheduler.episodes_one(_ctx(db, ["platforms"], platforms=[8], tmdb=FakeTMDB(on_netflix={1396}))))
    assert _messages(db) == ["Nouvel épisode de Breaking Bad sur Netflix : S01E02"]
    # Ajouté sur Plex
    asyncio.run(scheduler.episodes_one(_ctx(db, ["plex"], plex=FakePlex())))
    assert "Nouvel épisode de Breaking Bad sur Plex : S01E03 → S01E05" in _messages(db)  # regroupés
    # Pas de doublon au passage suivant
    asyncio.run(scheduler.episodes_one(_ctx(db, ["plex"], plex=FakePlex())))
    assert len(_messages(db)) == 2


def test_watchlist_title_added_on_plex(db):
    db.add(MediaState(tmdb_id=603, media_type="movie", title="Matrix", watchlist_sources='["local"]', availability_checked_at=utcnow() - timedelta(days=1)))
    db.commit()
    ctx = _ctx(db, via_movie=["plex"], plex=FakePlex())
    asyncio.run(scheduler.availability_one(ctx))
    assert _messages(db) == ["Matrix est maintenant disponible sur Plex"]
    asyncio.run(scheduler.availability_one(ctx))
    assert len(_messages(db)) == 1


def test_jellyfin_server_triggers(db):
    db.add(MediaState(tmdb_id=1396, media_type="tv", watchlist_sources='["local"]'))
    db.add(MediaState(tmdb_id=603, media_type="movie", title="Matrix", watchlist_sources='["local"]', availability_checked_at=utcnow() - timedelta(days=1)))
    db.commit()
    # « Ajouté sur le serveur » vaut aussi pour Jellyfin / Emby, avec le nom du serveur
    asyncio.run(scheduler.episodes_one(_ctx(db, ["plex"], jellyfin=FakeJellyfin())))
    asyncio.run(scheduler.availability_one(_ctx(db, via_movie=["plex"], jellyfin=FakeJellyfin())))
    assert _messages(db) == ["Matrix est maintenant disponible sur Jellyfin", "Nouvel épisode de Breaking Bad sur Jellyfin : S02E01"]


def test_jellyfin_recent_episodes(monkeypatch):
    from datetime import timezone

    from app.services.jellyfin_client import JellyfinClient

    now = datetime.now(timezone.utc)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")  # noqa: E731

    async def fake_req(self, method, path, ttl=0, token=None, json=None, **params):
        assert path == "/Items" and params["IncludeItemTypes"] == "Episode" and params["SortBy"] == "DateCreated"
        return {"Items": [
            {"SeriesId": "s1", "ParentIndexNumber": 1, "IndexNumber": 4, "DateCreated": iso(now - timedelta(hours=3))},
            {"SeriesId": "s1", "ParentIndexNumber": 1, "IndexNumber": 3, "DateCreated": iso(now - timedelta(days=5))},
        ]}

    monkeypatch.setattr(JellyfinClient, "_req", fake_req)
    eps = asyncio.run(JellyfinClient("http://jf.test", "k", "u1").recent_episodes(days=2))
    assert [(e["show_key"], e["season"], e["episode"]) for e in eps] == [("s1", 1, 4)]
