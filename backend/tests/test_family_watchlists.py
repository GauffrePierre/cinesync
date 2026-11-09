"""Watchlists partagées avec l'administrateur : seulement les comptes qui l'ont choisi, sans leur état personnel, et
seulement les titres que la personne ne peut pas regarder (ni sur ses plateformes, ni dans la bibliothèque)."""

from tests.test_accounts import client, fresh, member, setup_admin  # noqa: F401 (fixture)


def _add(c, tmdb_id, title, media_type="movie"):
    r = c.post("/api/library/watchlist", json={"tmdb_id": tmdb_id, "media_type": media_type, "title": title})
    assert r.status_code == 200, r.text


def test_admin_sees_only_shared_watchlists(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    alice, bob, carol = member(admin, "alice"), member(admin, "bob"), member(admin, "carol")
    _add(alice, 603, "Matrix")
    _add(alice, 1396, "Breaking Bad", "tv")
    alice.post("/api/library/rating", json={"tmdb_id": 603, "media_type": "movie", "title": "Matrix", "rating": 5})
    _add(bob, 603, "Matrix")
    _add(carol, 27205, "Inception")
    _add(admin, 155, "The Dark Knight")
    # Personne ne partage par défaut
    r = admin.get("/api/admin/watchlists").json()
    assert r["members"] == [] and r["shared"] == [] and r["not_sharing"] == 3
    assert alice.get("/api/settings").json()["share_watchlist"] is False
    # Alice et Bob partagent, Carol non
    for c in (alice, bob):
        assert c.put("/api/settings", json={"share_watchlist": True}).json()["share_watchlist"] is True
    r = admin.get("/api/admin/watchlists").json()
    assert [m["name"] for m in r["members"]] == ["Alice", "Bob"] and r["not_sharing"] == 1
    alice_items = r["members"][0]["items"]
    assert {i["title"] for i in alice_items} == {"Matrix", "Breaking Bad"}
    assert r["members"][0]["count"] == 2 and r["members"][0]["unavailable"] == 2
    assert all(set(i) <= {"id", "media_type", "title", "year", "poster", "release_date", "vote_average", "added", "in_plex", "plex_url"} for i in alice_items)
    assert "Inception" not in str(r) and "The Dark Knight" not in str(r)  # Carol et la watchlist de l'admin
    assert [(w["title"], sorted(w["members"])) for w in r["shared"]] == [("Matrix", ["Alice", "Bob"])]
    # Réservé aux administrateurs ; un membre ne voit pas les autres watchlists
    assert alice.get("/api/admin/watchlists").status_code == 403
    # Un titre sur une de ses plateformes : elle peut le regarder, il n'apparaît plus
    from sqlalchemy import update

    from app.database import SessionLocal
    from app.models import MediaState
    from app.services.clock import utcnow

    alice.put("/api/settings", json={"active_platforms": [8]})
    alice_id = r["members"][0]["id"]
    with SessionLocal() as db:
        db.execute(update(MediaState).where(MediaState.user_id == alice_id, MediaState.tmdb_id == 1396)
                   .values(providers='[{"id": 8, "name": "Netflix", "logo": null}]', providers_checked_at=utcnow())
                   .execution_options(all_users=True))
        db.commit()
    r = admin.get("/api/admin/watchlists").json()
    assert [i["title"] for i in r["members"][0]["items"]] == ["Matrix"] and r["members"][0]["count"] == 2
    # Partage retiré : aussitôt invisible
    alice.put("/api/settings", json={"share_watchlist": False})
    r = admin.get("/api/admin/watchlists").json()
    assert [m["name"] for m in r["members"]] == ["Bob"] and r["shared"] == []
