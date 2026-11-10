"""Aperçu des statistiques du Profil : d'après tout l'historique gardé par SynCiné, pas seulement Trakt."""

from datetime import timedelta

from app.database import SessionLocal
from app.models import MediaState, WatchEvent
from app.services.clock import utcnow
from tests.test_accounts import client, fresh, setup_admin  # noqa: F401 (fixture)


def test_profile_totals_come_from_every_source(fresh):  # noqa: F811
    admin = client()
    setup_admin(admin)
    now = utcnow()
    with SessionLocal() as db:
        db.add_all([
            WatchEvent(user_id=1, source="plex", source_key="p1", kind="movie", tmdb_id=603, title="Matrix", watched_at=now, runtime_min=136),
            WatchEvent(user_id=1, source="trakt", source_key="t1", kind="movie", tmdb_id=603, title="Matrix", watched_at=now - timedelta(days=400), runtime_min=136),
            WatchEvent(user_id=1, source="jellyfin", source_key="j1", kind="episode", tmdb_id=1396, show_title="Breaking Bad", season=1, episode=1,
                       watched_at=now, runtime_min=58),
            WatchEvent(user_id=1, source="jellyfin", source_key="j2", kind="episode", tmdb_id=1396, show_title="Breaking Bad", season=1, episode=2,
                       watched_at=now, runtime_min=48),
            MediaState(user_id=1, tmdb_id=27205, media_type="movie", title="Inception", watched_sources='["letterboxd"]'),
        ])
        db.commit()
    w = admin.get("/api/stats").json()["watched"]
    assert w == {"movies_watched": 2, "shows_watched": 1, "episodes_watched": 2, "hours": 6}  # revoir un film : compté une fois
