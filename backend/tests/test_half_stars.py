"""Notes par demi-étoile : 4,5 étoiles = 9/10 (Trakt, Plex), depuis la fiche, la watchlist et le mode swipe."""

from app.database import SessionLocal
from app.models import MediaState, SwipeHistory
from tests.test_accounts import client, fresh, setup_admin  # noqa: F401 (fixture)


def test_half_star_ratings(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    ref = {"tmdb_id": 603, "media_type": "movie", "title": "Matrix"}
    assert admin.post("/api/library/rating", json={**ref, "rating": 4.5}).status_code == 200
    assert admin.post("/api/library/rating", json={**ref, "rating": 4.3}).status_code == 422  # demi-étoiles seulement
    assert admin.post("/api/library/rating", json={**ref, "rating": 0}).status_code == 422
    assert admin.post("/api/swipe", json={"tmdb_id": 27205, "media_type": "movie", "title": "Inception", "action": "seen", "rating": 3.5}).status_code == 200
    with SessionLocal() as db:
        ratings = {r.tmdb_id: r.rating for r in db.query(MediaState).execution_options(all_users=True)}
        swipe = db.query(SwipeHistory).execution_options(all_users=True).one()
    assert ratings == {603: 9, 27205: 7}  # sur 10
    assert swipe.rating == 3  # mémoire du swipe en étoiles entières
