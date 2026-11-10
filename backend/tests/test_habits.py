"""Habitudes du soir (épisodes ou films selon le jour) et séries presque finies, pour « Pour ce soir »."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from app.models import WatchEvent
from app.services import habits
from app.services.clock import utcnow


def _ev(n, kind, at, tmdb=1, season=None, episode=None):
    return WatchEvent(source="trakt", source_key=f"k{n}", kind=kind, tmdb_id=tmdb, title="T", season=season, episode=episode, watched_at=at)


def test_evening_habit_by_weekday(db):
    base = utcnow().replace(hour=20, minute=0, second=0, microsecond=0)
    wednesday = base - timedelta(days=(base.weekday() - 2) % 7)
    saturday = base - timedelta(days=(base.weekday() - 5) % 7)
    n = 0
    for w in range(6):  # 6 mercredis d'épisodes, 6 samedis de films (et un samedi série)
        db.add(_ev(n, "episode", wednesday - timedelta(weeks=w), season=1, episode=w + 1)); n += 1
        db.add(_ev(n, "movie", saturday - timedelta(weeks=w), tmdb=100 + w)); n += 1
    db.add(_ev(n, "episode", saturday - timedelta(weeks=7), season=2, episode=1))
    db.commit()
    ctx = SimpleNamespace(db=db)
    assert habits.evening_habit(ctx, 2)["prefer"] == "tv"
    assert habits.evening_habit(ctx, 5)["prefer"] == "movie"
    assert habits.evening_habit(ctx, 0) is None  # aucun lundi : pas d'habitude


class Tmdb:
    async def _get(self, path, ttl=0):
        tid = int(path.rsplit("/", 1)[1])
        return {  # série 1 : 2 saisons de 6, sortie jusqu'à S2E6 ; série 2 : 3 saisons de 10
            1: {"seasons": [{"season_number": 0, "episode_count": 3}, {"season_number": 1, "episode_count": 6}, {"season_number": 2, "episode_count": 6}],
                "last_episode_to_air": {"season_number": 2, "episode_number": 6}},
            2: {"seasons": [{"season_number": s, "episode_count": 10} for s in (1, 2, 3)], "last_episode_to_air": {"season_number": 3, "episode_number": 10}},
        }[tid]


def test_nearly_finished_series(db):
    now = utcnow()
    n = 0
    for s, e in [(1, x) for x in range(1, 7)] + [(2, x) for x in range(1, 4)]:  # série 1 : il reste 3 épisodes
        db.add(_ev(n, "episode", now - timedelta(days=2), tmdb=1, season=s, episode=e)); n += 1
    for e in range(1, 4):  # série 2 : il en reste 27, pas « presque finie »
        db.add(_ev(n, "episode", now - timedelta(days=5), tmdb=2, season=1, episode=e)); n += 1
    db.commit()
    out = asyncio.run(habits.nearly_finished(SimpleNamespace(db=db, tmdb=Tmdb())))
    assert out == [{"tmdb_id": 1, "remaining": 3}]
