"""Tests de la synchronisation Trakt <-> Plex (pull + synchro bidirectionnelle + actions).

Les faux services n'écrivent nulle part : ils enregistrent les appels, qu'on vérifie ensuite.
"""

import asyncio

from sqlalchemy import select

from app.models import MediaState
from app.services import library_sync
from tests.conftest import FakeCtx, FakePlexAccount, FakePlexServer, FakeTrakt, lib_item

A, B, C, D = ("movie", 1), ("movie", 2), ("tv", 3), ("movie", 4)


def pull(ctx):
    return asyncio.run(library_sync.pull(ctx))


def row(db, key):
    return db.execute(select(MediaState).where(MediaState.media_type == key[0], MediaState.tmdb_id == key[1])).scalar_one_or_none()


def trakt_paths(trakt, path):
    return [refs for p, refs in trakt.calls if p == path]


def keys_of(refs):
    return {(r[0], r[1]) for r in refs}


# --- Watchlist -----------------------------------------------------------------------


def test_first_sync_copies_missing_titles_both_ways(db):
    trakt = FakeTrakt(watchlist=[C])
    plex = FakePlexAccount(watchlist=[A, B])
    result = pull(FakeCtx(db, trakt=trakt, plex_account=plex))

    assert keys_of(trakt_paths(trakt, "/sync/watchlist")[0]) == {A, B}
    assert ("add", C) in plex.calls
    assert not trakt_paths(trakt, "/sync/watchlist/remove")
    assert not [c for c in plex.calls if c[0] == "remove"]
    assert result["pushed"]["added"] == {"trakt": 2, "plex": 1}
    # Passage suivant : les services contiennent tout -> état confirmé, plus aucune écriture
    trakt2, plex2 = FakeTrakt(watchlist=[A, B, C]), FakePlexAccount(watchlist=[A, B, C])
    pull(FakeCtx(db, trakt=trakt2, plex_account=plex2))
    assert trakt2.calls == [] and plex2.calls == []
    for k in (A, B, C):
        assert row(db, k).sources("watchlist") >= {"trakt", "plex"}


def test_title_removed_on_one_side_is_removed_on_the_other(db):
    # 1re synchro : A des deux côtés
    pull(FakeCtx(db, trakt=FakeTrakt(watchlist=[A, B]), plex_account=FakePlexAccount(watchlist=[A, B])))
    # Retiré de Plex depuis : doit être retiré de Trakt, pas recopié sur Plex
    trakt = FakeTrakt(watchlist=[A, B])
    plex = FakePlexAccount(watchlist=[B])
    pull(FakeCtx(db, trakt=trakt, plex_account=plex))

    assert keys_of(trakt_paths(trakt, "/sync/watchlist/remove")[0]) == {A}
    assert ("add", A) not in plex.calls
    # Passage suivant : retiré des deux côtés -> plus dans la watchlist, et pas recopié
    trakt3, plex3 = FakeTrakt(watchlist=[B]), FakePlexAccount(watchlist=[B])
    pull(FakeCtx(db, trakt=trakt3, plex_account=plex3))
    assert not row(db, A).in_watchlist
    assert trakt3.calls == [] and plex3.calls == []


def test_massive_disappearance_is_not_propagated(db):
    many = [("movie", i) for i in range(100, 130)]
    pull(FakeCtx(db, trakt=FakeTrakt(watchlist=many), plex_account=FakePlexAccount(watchlist=many)))
    # Plex renvoie soudain une watchlist vide (erreur de lecture probable)
    trakt = FakeTrakt(watchlist=many)
    plex = FakePlexAccount(watchlist=[])
    result = pull(FakeCtx(db, trakt=trakt, plex_account=plex))

    assert not trakt_paths(trakt, "/sync/watchlist/remove")
    assert not [c for c in plex.calls if c[0] == "add"]  # ni retrait, ni recopie
    assert any("sécurité" in w for w in result["pushed"]["warnings"])


def test_trakt_watchlist_limit_keeps_most_recent(db):
    trakt = FakeTrakt(watchlist=[], limit=2)
    plex = FakePlexAccount(watchlist=[A, B, C, D])  # Plex renvoie du plus récent au plus ancien
    result = pull(FakeCtx(db, trakt=trakt, plex_account=plex))

    assert keys_of(trakt_paths(trakt, "/sync/watchlist")[0]) == {A, B}
    assert any("limitée à 2" in w for w in result["pushed"]["warnings"])


def test_auto_sync_disabled_writes_nothing(db):
    trakt = FakeTrakt(watchlist=[C])
    plex = FakePlexAccount(watchlist=[A])
    pull(FakeCtx(db, trakt=trakt, plex_account=plex, auto_sync=False))

    assert trakt.calls == [] and plex.calls == []
    assert row(db, A).sources("watchlist") == {"plex"}  # la collecte, elle, a bien eu lieu


def test_failing_service_keeps_its_data_and_is_not_synced(db):
    pull(FakeCtx(db, trakt=FakeTrakt(watchlist=[A]), plex_account=FakePlexAccount(watchlist=[A])))
    trakt = FakeTrakt(fail=True)
    plex = FakePlexAccount(watchlist=[A])
    result = pull(FakeCtx(db, trakt=trakt, plex_account=plex))

    assert result["sources"]["trakt"]["ok"] is False
    assert "trakt" in row(db, A).sources("watchlist")  # données Trakt conservées
    assert ("remove", ("movie", 1)) not in plex.calls


# --- Vus et notes --------------------------------------------------------------------


def test_watched_rules_between_plex_and_trakt(db):
    server = FakePlexServer(
        [
            lib_item("movie", 10, "r10", view_count=1, last_viewed_at="2026-03-01T20:00:00+00:00"),
            lib_item("tv", 11, "r11", episodes=10, viewed_episodes=10),  # série entièrement vue
            lib_item("tv", 12, "r12", episodes=10, viewed_episodes=3),  # partiellement : pas « vue »
            lib_item("movie", 13, "r13"),  # dans la bibliothèque, pas vu
        ]
    )
    trakt = FakeTrakt(watched=[("movie", 13), ("movie", 14), ("tv", 15)])
    plex = FakePlexAccount()
    pull(FakeCtx(db, trakt=trakt, plex_account=plex, plex=server))

    history = trakt_paths(trakt, "/sync/history")[0]
    assert keys_of(history) == {("movie", 10), ("tv", 11)}
    dated = [r for r in history if (r[0], r[1]) == ("movie", 10)][0]
    assert dated[2]["watched_at"].startswith("2026-03-01")
    # Vers Plex : films seulement ; via le serveur s'il a le titre, sinon via le compte
    assert ("scrobble", "r13") in server.calls
    assert ("watched", ("movie", 14)) in plex.calls
    assert not [c for c in plex.calls if c[0] == "watched" and c[1][0] == "tv"]


def test_ratings_priority_and_push(db):
    server = FakePlexServer([lib_item("movie", 1, "r1", user_rating=6), lib_item("movie", 2, "r2", user_rating=7)])
    trakt = FakeTrakt(ratings={A: 8})
    pull(FakeCtx(db, trakt=trakt, plex_account=FakePlexAccount(), plex=server))

    assert row(db, A).rating == 8 and row(db, A).rating_source == "trakt"  # Trakt prioritaire
    assert trakt_paths(trakt, "/sync/ratings")[0] == [("movie", 2, 7)]  # seule la note manquante part
    assert not [c for c in server.calls if c[0] == "rate"]  # A est déjà noté côté Plex


# --- Actions faites dans CinéSync ------------------------------------------------------


def test_action_saved_locally_even_if_a_service_fails(db):
    ctx = FakeCtx(db, trakt=FakeTrakt(), plex_account=FakePlexAccount(fail_writes=True))
    res = asyncio.run(library_sync.act(ctx, "watchlist_add", "movie", 42, title="Test"))

    assert res["services"]["trakt"] == "ok"
    assert res["services"]["plex"] == "Plex refuse"
    assert row(db, ("movie", 42)).sources("watchlist") == {"trakt", "local"}


def test_remove_action_keeps_source_of_failed_service(db):
    asyncio.run(library_sync.act(FakeCtx(db, trakt=FakeTrakt(), plex_account=FakePlexAccount()), "watchlist_add", "movie", 7))
    ctx = FakeCtx(db, trakt=FakeTrakt(), plex_account=FakePlexAccount(fail_writes=True))
    asyncio.run(library_sync.act(ctx, "watchlist_remove", "movie", 7))

    assert row(db, ("movie", 7)).sources("watchlist") == {"plex"}  # encore sur Plex, retrait à refaire


def test_show_history_sent_with_real_episode_dates(db):
    from datetime import datetime

    from app.models import WatchEvent

    db.add_all([
        WatchEvent(source="plex", source_key="a", plex_account_id=1, kind="episode", tmdb_id=11, season=1, episode=1, watched_at=datetime(2025, 2, 3, 21, 0)),
        WatchEvent(source="plex", source_key="b", plex_account_id=1, kind="episode", tmdb_id=11, season=1, episode=2, watched_at=datetime(2025, 2, 4, 21, 0)),
        WatchEvent(source="plex", source_key="c", plex_account_id=999, kind="episode", tmdb_id=11, season=1, episode=3, watched_at=datetime(2025, 2, 5, 21, 0)),
    ])
    db.commit()
    server = FakePlexServer([lib_item("tv", 11, "r11", episodes=2, viewed_episodes=2), lib_item("tv", 12, "r12", episodes=1, viewed_episodes=1)])
    trakt = FakeTrakt()
    pull(FakeCtx(db, trakt=trakt, plex_account=FakePlexAccount(), plex=server))

    entries = {(r[0], r[1]): r[2] for r in trakt_paths(trakt, "/sync/history")[0]}
    seasons = entries[("tv", 11)]["seasons"]
    assert seasons == [{"number": 1, "episodes": [
        {"number": 1, "watched_at": "2025-02-03T21:00:00.000Z"},
        {"number": 2, "watched_at": "2025-02-04T21:00:00.000Z"},
    ]}]  # l'épisode vu par un autre compte Plex n'est pas envoyé
    assert entries[("tv", 12)] == {"watched_at": "released"}  # jamais l'heure de l'envoi


def test_titles_unknown_to_trakt_are_not_resent(db):
    server = FakePlexServer([lib_item("movie", 50, "r50", view_count=1)])
    trakt = FakeTrakt(not_found=[("movie", 50)])
    pull(FakeCtx(db, trakt=trakt, plex_account=FakePlexAccount(), plex=server))
    assert len(trakt_paths(trakt, "/sync/history")) == 1
    trakt2 = FakeTrakt(not_found=[("movie", 50)])
    pull(FakeCtx(db, trakt=trakt2, plex_account=FakePlexAccount(), plex=server))
    assert trakt_paths(trakt2, "/sync/history") == []


def test_trakt_lists_are_read_across_all_pages(db, monkeypatch):
    from app.models import UserSettings
    from app.services.trakt_client import TraktClient

    s = db.get(UserSettings, 1)
    s.trakt_client_id, s.trakt_access_token = "cid", "tok"
    client = TraktClient(s, db)
    pages = {1: [{"type": "movie", "movie": {"ids": {"tmdb": i}}} for i in range(1, 251)], 2: [{"type": "movie", "movie": {"ids": {"tmdb": 1000}}}]}

    async def fake_request(method, path, *, params=None, meta=None, **kw):
        if meta is not None:
            meta["pages"] = 2
        return pages[params["page"]] if "movies" in path else []

    monkeypatch.setattr(client, "_request", fake_request)
    wl = asyncio.run(client.watchlist())
    assert len(wl) == 251  # avant le correctif : seulement la 1re page


def test_title_refused_by_trakt_is_not_removed_from_plex(db):
    # 1er passage : Trakt refuse A (introuvable) -> ne doit jamais passer pour « retiré de Trakt »
    trakt = FakeTrakt(not_found=[A])
    pull(FakeCtx(db, trakt=trakt, plex_account=FakePlexAccount(watchlist=[A])))
    trakt2, plex2 = FakeTrakt(not_found=[A]), FakePlexAccount(watchlist=[A])
    pull(FakeCtx(db, trakt=trakt2, plex_account=plex2))
    assert not [c for c in plex2.calls if c[0] == "remove"]
    assert trakt_paths(trakt2, "/sync/watchlist") == []  # pas de nouvel essai en boucle


def test_unwatch_and_unlike_toggle_everywhere(db):
    trakt, plex = FakeTrakt(), FakePlexAccount()
    ctx = FakeCtx(db, trakt=trakt, plex_account=plex)
    asyncio.run(library_sync.act(ctx, "watched", "movie", 8))
    asyncio.run(library_sync.act(ctx, "like", "movie", 8))
    asyncio.run(library_sync.act(ctx, "unwatched", "movie", 8))
    asyncio.run(library_sync.act(ctx, "unlike", "movie", 8))
    r = row(db, ("movie", 8))
    assert not r.watched and not r.liked
    assert ("unhistory", ("movie", 8)) in trakt.calls and ("unfavorite", ("movie", 8)) in trakt.calls
    assert ("unwatched", ("movie", 8)) in plex.calls


def test_dislike_hides_title_from_suggestions_and_trakt(db):
    from app.services.suggestions import excluded_keys

    trakt = FakeTrakt()
    ctx = FakeCtx(db, trakt=trakt)
    asyncio.run(library_sync.act(ctx, "like", "movie", 9))
    asyncio.run(library_sync.act(ctx, "dislike", "movie", 9))
    r = row(db, ("movie", 9))
    assert r.disliked and not r.liked
    assert ("hide", ("movie", 9)) in trakt.calls
    ctx.trakt = None  # excluded_keys interroge Trakt seulement s'il est connecté
    assert ("movie", 9) in asyncio.run(excluded_keys(ctx))
