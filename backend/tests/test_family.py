"""Suggestions en famille : seulement entre comptes qui partagent leurs goûts, rien d'un compte qui ne partage pas."""

import asyncio
from types import SimpleNamespace

from app.database import SessionLocal
from app.models import MediaState, User
from app.services import family
from app.services.context import settings_for
from tests.test_accounts import client, fresh, member, setup_admin  # noqa: F401 (fixture)


def _item(tid, title, mt="movie"):
    return {"id": tid, "media_type": mt, "title": title, "genre_ids": [], "vote_count": 500, "vote_average": 7.5}


class Tmdb:
    is_mock = False

    def __init__(self, recs=None):
        self.recs = recs or {}

    async def recommendations(self, media_type, tmdb_id):
        return self.recs.get((media_type, tmdb_id), [])

    async def basic(self, media_type, tmdb_id):
        return _item(tmdb_id, f"T{tmdb_id}", media_type)

    async def features_raw(self, media_type, tmdb_id):
        return {}


async def _no_enrich(ctx, items, **kw):
    return items


def _ctx(db, uid, recs=None):
    from app.database import bind_user

    bind_user(db, uid)
    return SimpleNamespace(db=db, user=db.get(User, uid), settings=settings_for(db, uid), tmdb=Tmdb(recs), trakt=None, platforms=[])


def _rows(uid, rows):
    with SessionLocal() as db:
        for kw in rows:
            db.add(MediaState(user_id=uid, **kw))
        db.commit()


def test_family_sharing_is_mutual_and_private(fresh, monkeypatch):  # noqa: F811
    monkeypatch.setattr(family, "enrich", _no_enrich)
    monkeypatch.setattr(family, "refs_to_items", lambda ctx, refs: asyncio.sleep(0, [_item(r["tmdb_id"], f"T{r['tmdb_id']}", r["media_type"]) for r in refs]))
    admin = client()
    setup_admin(admin)
    alice, bob, carol = member(admin, "alice"), member(admin, "bob"), member(admin, "carol")
    ids = {u["username"]: u["id"] for u in admin.get("/api/admin/users").json()["results"]}
    _rows(ids["alice"], [{"tmdb_id": 10, "media_type": "movie", "title": "Aimé d'Alice", "liked": True},
                         {"tmdb_id": 30, "media_type": "movie", "title": "Commun", "watchlist_sources": '["local"]'}])
    _rows(ids["bob"], [{"tmdb_id": 20, "media_type": "movie", "title": "Aimé de Bob", "liked": True},
                       {"tmdb_id": 30, "media_type": "movie", "title": "Commun", "watchlist_sources": '["local"]'}])
    _rows(ids["carol"], [{"tmdb_id": 40, "media_type": "movie", "title": "Aimé de Carol", "liked": True}])
    # Personne ne partage : rien
    assert alice.get("/api/media/family/partners").json() == {"sharing": False, "results": []}
    assert alice.get("/api/media/family").json()["results"] == []
    # Alice et Bob partagent, Carol non
    for c in (alice, bob):
        assert c.put("/api/settings", json={"share_taste": True}).json()["share_taste"] is True
    assert [p["name"] for p in alice.get("/api/media/family/partners").json()["results"]] == ["Bob"]
    assert carol.get("/api/media/family/partners").json()["results"] == []  # Carol ne partage pas : elle ne voit personne
    with SessionLocal() as db:
        loved = asyncio.run(family.family_loved(_ctx(db, ids["alice"])))
    assert [i["id"] for i in loved] == [20] and loved[0]["reason_params"] == {"names": "Bob"}  # rien de Carol
    # À deux : refusé avec un compte qui ne partage pas
    assert alice.get("/api/tonight", params={"with_user": ids["carol"]}).status_code == 404
    assert alice.get("/api/tonight", params={"with_user": ids["bob"]}).status_code == 200
    with SessionLocal() as db:
        both = asyncio.run(family.common_watchlist(_ctx(db, ids["alice"]), [ids["bob"]]))
    assert [i["id"] for i in both] == [30]


def test_together_puts_shared_tastes_first(db, monkeypatch):
    monkeypatch.setattr(family, "enrich", _no_enrich)
    with SessionLocal() as s:
        s.add(User(username="bob", display_name="Bob", role="member"))
        s.commit()
        bob_id = s.query(User).filter(User.username == "bob").one().id
        s.add_all([MediaState(user_id=1, tmdb_id=1, media_type="movie", title="A", liked=True),
                   MediaState(user_id=bob_id, tmdb_id=2, media_type="movie", title="B", liked=True),
                   MediaState(user_id=bob_id, tmdb_id=105, media_type="movie", title="Déjà vu par Bob", watched_sources='["trakt"]')])
        s.commit()
    recs = {("movie", 1): [_item(100, "Pour moi"), _item(101, "Pour nous"), _item(105, "Déjà vu par Bob")],
            ("movie", 2): [_item(101, "Pour nous"), _item(102, "Pour Bob")]}
    out = asyncio.run(family.together(_ctx(db, 1, recs), [(bob_id, "Bob")], "movie"))
    assert out[0]["title"] == "Pour nous" and out[0]["reason_key"] == "Pour vous deux"
    assert "Déjà vu par Bob" not in [i["title"] for i in out]
    bob_pick = next(i for i in out if i["title"] == "Pour Bob")
    assert bob_pick["reason_key"] == "Parce que {name} a aimé {title}" and bob_pick["reason_params"] == {"name": "Bob", "title": "B"}


def test_group_of_three_and_member_filter(fresh, monkeypatch):  # noqa: F811
    monkeypatch.setattr(family, "enrich", _no_enrich)
    monkeypatch.setattr(family, "refs_to_items", lambda ctx, refs: asyncio.sleep(0, [_item(r["tmdb_id"], f"T{r['tmdb_id']}", r["media_type"]) for r in refs]))
    admin = client()
    setup_admin(admin)
    alice, bob, carol = member(admin, "alice"), member(admin, "bob"), member(admin, "carol")
    ids = {u["username"]: u["id"] for u in admin.get("/api/admin/users").json()["results"]}
    for c in (alice, bob, carol):
        c.put("/api/settings", json={"share_taste": True})
    _rows(ids["alice"], [{"tmdb_id": 1, "media_type": "movie", "title": "A", "liked": True}])
    _rows(ids["bob"], [{"tmdb_id": 2, "media_type": "movie", "title": "B", "liked": True}])
    _rows(ids["carol"], [{"tmdb_id": 3, "media_type": "movie", "title": "C", "liked": True}])
    recs = {("movie", 1): [_item(100, "Pour tous"), _item(101, "Pour Alice")], ("movie", 2): [_item(100, "Pour tous")], ("movie", 3): [_item(100, "Pour tous")]}
    with SessionLocal() as db:
        out = asyncio.run(family.together(_ctx(db, ids["alice"], recs), [(ids["bob"], "Bob"), (ids["carol"], "Carol")], "movie"))
        assert out[0]["title"] == "Pour tous" and out[0]["reason_key"] == "Pour vous tous"
        only_bob = asyncio.run(family.family_loved(_ctx(db, ids["alice"]), only=[ids["bob"]]))
        assert [i["id"] for i in only_bob] == [2]  # seulement les coups de cœur de Bob
    assert alice.get("/api/tonight", params={"with_users": f"{ids['bob']},{ids['carol']}"}).status_code == 200
    assert alice.get("/api/tonight", params={"with_users": f"{ids['bob']},999"}).status_code == 404


def test_kids_setting_and_age_rule(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    s = admin.put("/api/settings", json={"family_kids": ["enfants", "petits"]}).json()
    assert s["family_kids"] == ["enfants", "petits"]
    assert admin.put("/api/settings", json={"family_kids": ["bebes"]}).status_code == 422
    assert admin.get("/api/tonight", params={"kids": "true"}).json()["kids"] is True
