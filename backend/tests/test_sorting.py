"""Tris communs et infos de tri de la watchlist."""

import asyncio
from types import SimpleNamespace

from app.models import MediaState, User
from app.services.sorting import fill_info, sort_items
from tests.test_accounts import client, fresh, setup_admin  # noqa: F401 (fixture)

ITEMS = [
    {"id": 1, "title": "beta", "year": 1999, "release_date": "1999-03-31", "vote_average": 8.7, "critic_score": 83, "audience_score": None, "personal_rating": 10, "added": "2026-01-01"},
    {"id": 2, "title": "Alpha", "year": 2024, "release_date": "2024-02-28", "vote_average": 8.1, "critic_score": 92, "audience_score": 95, "personal_rating": None, "added": "2026-03-01"},
    {"id": 3, "title": "gamma", "year": None, "release_date": None, "vote_average": 0, "critic_score": None, "audience_score": 70, "personal_rating": 6, "added": None},
]


def ids(sort):
    return [i["id"] for i in sort_items([dict(i) for i in ITEMS], sort)]


def test_sorts_put_missing_values_last():
    assert ids("title") == [2, 1, 3]
    assert ids("release") == [2, 1, 3]
    assert ids("year") == [2, 1, 3]
    assert ids("rating") == [1, 2, 3]
    assert ids("critics") == [2, 1, 3]
    assert ids("audience") == [2, 3, 1]
    assert ids("personal") == [1, 3, 2]
    assert ids("added") == [2, 1, 3]


class FakeTMDB:
    is_mock = False

    async def basic(self, media_type, tmdb_id):
        return {"release_date": f"20{tmdb_id}-01-01", "vote_average": tmdb_id / 10, "year": 2000 + tmdb_id}


class FakeAccount:
    async def scores(self, media_type, tmdb_id):
        return {"rt_critic": 90, "imdb": 7.5} if tmdb_id == 10 else {}


def test_fill_info(db):
    db.add_all([MediaState(tmdb_id=i, media_type="movie", watchlist_sources='["local"]') for i in (10, 20)])
    db.commit()
    rows = db.query(MediaState).all()
    ctx = SimpleNamespace(db=db, user=db.get(User, 1), tmdb=FakeTMDB(), plex_account=FakeAccount())
    assert asyncio.run(fill_info(ctx, rows, scores=False)) == 2
    assert rows[0].info_checked_at is None and rows[0].tmdb_rating == 1.0  # TMDB seulement, à compléter plus tard
    assert asyncio.run(fill_info(ctx, rows)) == 2
    r10 = next(r for r in rows if r.tmdb_id == 10)
    assert (r10.critic_score, r10.audience_score, r10.release_date) == (90, 75, "2010-01-01")
    assert asyncio.run(fill_info(ctx, rows)) == 0  # à jour pour 7 jours


def test_watchlist_accepts_the_new_sorts(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    admin.post("/api/library/watchlist", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix"})
    for sort in ("added", "release", "title", "year", "rating", "critics", "audience", "personal"):
        r = admin.get(f"/api/library/watchlist?sort={sort}")
        assert r.status_code == 200, sort
    assert admin.get("/api/library/watchlist?sort=bogus").status_code == 422
    assert admin.get("/api/tonight?sort=critics&mood=pepites").status_code == 200


def test_tonight_seen_filter(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    for seen in ("unseen", "seen", "all"):
        r = admin.get(f"/api/tonight?seen={seen}")
        assert r.status_code == 200 and "rewatch" in r.json()["sections"], seen
    assert admin.get("/api/tonight?seen=bogus").status_code == 422
