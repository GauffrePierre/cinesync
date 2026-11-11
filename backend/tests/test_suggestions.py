"""Moteur de suggestions : références de toutes les sources, variété, disponibilité et part de découverte."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from app.models import MediaState, SuggestionShown, SwipeHistory, User, WatchEvent
from app.services import suggestions as sg
from app.services.clock import utcnow
from tests.test_accounts import client, fresh, member, setup_admin  # noqa: F401 (fixture)


def _item(tid, title, mt="movie", genres=()):
    return {"id": tid, "media_type": mt, "title": title, "genre_ids": list(genres)}


class Tmdb:
    is_mock = False

    def __init__(self, recs):
        self.recs = recs  # (type, id) -> recommandations

    async def recommendations(self, media_type, tmdb_id):
        return self.recs.get((media_type, tmdb_id), [])

    async def discover(self, media_type, **kw):
        return []

    async def basic(self, media_type, tmdb_id):
        return None

    async def features_raw(self, media_type, tmdb_id):
        return getattr(self, "raw", {}).get((media_type, tmdb_id), {})


def _ctx(db, recs, platforms=(8,)):
    return SimpleNamespace(db=db, user=db.get(User, 1), tmdb=Tmdb(recs), trakt=None, platforms=list(platforms))


def _fake_enrich(available_ids):
    async def enrich(ctx, items, **kw):
        for i in items:
            i["providers"] = [{"id": 8, "name": "Netflix"}] if i["id"] in available_ids else []
            i["in_plex"] = False
        return items
    return enrich


def test_seeds_use_every_source(db):
    now = utcnow()
    db.add_all([
        MediaState(tmdb_id=1, media_type="movie", title="Coup de cœur", liked=True, watched_sources='["trakt"]', watched_at=now.isoformat()),
        MediaState(tmdb_id=2, media_type="movie", title="Noté 10", rating=10, rating_source="letterboxd", watched_sources='["letterboxd"]'),
        MediaState(tmdb_id=3, media_type="movie", title="Noté 2", rating=2, watched_sources='["plex"]'),
        MediaState(tmdb_id=4, media_type="movie", title="Pas intéressé", disliked=True),
        MediaState(tmdb_id=5, media_type="tv", title="En watchlist", watchlist_sources='["local"]', listed_at=now.isoformat()),
        SwipeHistory(tmdb_id=6, media_type="movie", action="like", title="Swipé"),
        SwipeHistory(tmdb_id=7, media_type="movie", action="skip", title="Passé"),
    ])
    for n in range(8):  # série suivie dans l'historique (Plex, Jellyfin…)
        db.add(WatchEvent(source="jellyfin", source_key=f"e{n}", kind="episode", tmdb_id=9, show_title="Série suivie", season=1, episode=n + 1,
                          watched_at=now - timedelta(days=3)))
    db.commit()
    pos, neg = sg.seeds(_ctx(db, {}), ["movie", "tv"])
    keys = {(s["media_type"], s["tmdb_id"]) for s in pos}
    assert {("movie", 1), ("movie", 2), ("movie", 6), ("tv", 9), ("tv", 5)} <= keys
    assert ("movie", 7) not in keys and ("movie", 4) not in keys and ("movie", 3) not in keys
    assert {(s["media_type"], s["tmdb_id"]) for s in neg} == {("movie", 3), ("movie", 4)}  # mal noté, pas intéressé
    assert pos[0]["tmdb_id"] in (1, 2, 6)  # coups de cœur et meilleures notes d'abord
    again = sg.seeds(_ctx(db, {}), ["movie", "tv"])
    ids = lambda lst: [(s["media_type"], s["tmdb_id"]) for s in lst]  # noqa: E731
    assert (ids(again[0]), ids(again[1])) == (ids(pos), ids(neg))  # même tirage toute la journée


def test_variety_penalties_and_discovery(db, monkeypatch):
    db.add_all([
        MediaState(tmdb_id=1, media_type="movie", title="A", liked=True),
        MediaState(tmdb_id=2, media_type="movie", title="Navet", rating=2, watched_sources='["trakt"]'),
    ])
    db.commit()
    recs = {
        ("movie", 1): [_item(100, "Dune"), _item(101, "Dune : Deuxième partie"), _item(102, "Alien"), _item(103, "Blade Runner"),
                       _item(104, "Arrival"), _item(105, "Interstellar")],
        ("movie", 2): [_item(105, "Interstellar")],  # proche d'un titre mal noté
    }
    monkeypatch.setattr(sg, "enrich", _fake_enrich({102, 103}))
    out = asyncio.run(sg.suggestions(_ctx(db, recs), "movie", limit=10))
    titles = [i["title"] for i in out]
    assert len(titles) == 3  # au plus 3 par référence
    assert "Dune : Deuxième partie" not in titles  # une seule par saga
    assert titles[0] in ("Alien", "Blade Runner")  # disponible sur mes plateformes : devant
    # Part de découverte : au moins 30 % de titres que je n'ai pas
    small = asyncio.run(sg.suggestions(_ctx(db, recs), "movie", limit=3))
    assert any(i["id"] not in (102, 103) for i in small)
    only = asyncio.run(sg.suggestions(_ctx(db, recs), "movie", limit=3, available_only=True))
    assert {i["id"] for i in only} <= {102, 103}
    # Titre proche d'un navet : en retrait
    assert "Interstellar" not in titles[:1]


def test_often_shown_titles_step_back(db, monkeypatch):
    db.add(MediaState(tmdb_id=1, media_type="movie", title="A", liked=True))
    db.commit()
    recs = {("movie", 1): [_item(100, "Premier"), _item(101, "Second")]}
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    ctx = _ctx(db, recs)
    assert [i["id"] for i in asyncio.run(sg.suggestions(ctx, "movie", limit=2))] == [100, 101]
    db.add(SuggestionShown(media_type="movie", tmdb_id=100, count=6, last_shown=utcnow()))
    db.commit()
    assert [i["id"] for i in asyncio.run(sg.suggestions(ctx, "movie", limit=2))] == [101, 100]
    # Une présentation compte au plus une fois toutes les 12 heures
    sg.record_shown(ctx, [{"media_type": "movie", "id": 100}, {"media_type": "movie", "id": 101}])
    sg.record_shown(ctx, [{"media_type": "movie", "id": 101}])
    counts = {r.tmdb_id: r.count for r in db.query(SuggestionShown)}
    assert counts == {100: 6, 101: 1}


def test_movies_and_series_mixed_and_unknown_titles_step_back(db, monkeypatch):
    db.add_all([MediaState(tmdb_id=1, media_type="movie", title="A", liked=True), MediaState(tmdb_id=2, media_type="tv", title="B", liked=True)])
    db.commit()
    movies = [_item(100 + n, f"Film {chr(65 + n)}") | {"vote_count": 500, "vote_average": 7.5} for n in range(3)]
    obscure = _item(150, "Inconnu") | {"vote_count": 3, "vote_average": 9, "release_date": "2001-01-01"}
    series = [_item(200 + n, f"Série {chr(65 + n)}", "tv") | {"vote_count": 500, "vote_average": 7.5} for n in range(3)]
    recs = {("movie", 1): [obscure] + movies, ("tv", 2): series}
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    out = asyncio.run(sg.suggestions(_ctx(db, recs), "all", limit=6))
    types = [i["media_type"] for i in out]
    assert types.count("tv") >= 2 and "tv" in types[:3]  # séries mêlées aux films, pas toutes à la fin
    assert out[0]["title"] != "Inconnu"  # presque aucun vote : en retrait


def test_recent_known_and_well_rated_titles_come_first(db, monkeypatch):
    """À recommandation égale, ce qui est sorti dans l'année, connu et bien noté passe devant (ce que montrent les
    historiques réels) ; un titre obscur ou mal noté recule, sans disparaître."""
    recent = (utcnow() - timedelta(days=90)).date().isoformat()
    five_years = (utcnow() - timedelta(days=5 * 365)).date().isoformat()
    old = _item(100, "Ancien") | {"vote_count": 3000, "vote_average": 7.5, "release_date": five_years}
    new = _item(101, "Récent") | {"vote_count": 3000, "vote_average": 7.5, "release_date": recent}
    assert sg._prior(new) == sg.RECENT_BOOST * sg._prior(old)
    assert sg._prior(old | {"vote_count": 60}) < 0.4 * sg._prior(old)  # presque inconnu
    assert sg._prior(old | {"vote_average": 5.5}) < 0.3 * sg._prior(old)  # mal noté
    assert sg._prior(old | {"vote_average": 8.2}) > 2 * sg._prior(old)  # très bien noté
    assert sg._prior(_item(102, "Sans date") | {"vote_count": 0, "vote_average": 0}) > 0  # jamais nul, jamais d'erreur
    db.add(MediaState(tmdb_id=1, media_type="movie", title="A", liked=True))
    db.commit()
    bad = _item(103, "Mal noté") | {"vote_count": 3000, "vote_average": 5.2, "release_date": five_years}
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    out = asyncio.run(sg.suggestions(_ctx(db, {("movie", 1): [bad, old, new]}), "movie", limit=3))
    assert [i["title"] for i in out] == ["Récent", "Ancien", "Mal noté"]  # l'ordre de TMDB était l'inverse


def test_recent_releases_join_the_candidates_within_a_cap(db, monkeypatch):
    """Les sorties de l'année les plus suivies s'ajoutent aux candidats (même sans rapport avec une référence), mais
    restent une part limitée de la liste : PER_SEED par type."""
    recent = (utcnow() - timedelta(days=60)).date().isoformat()
    asked = []

    class WithReleases(Tmdb):
        async def discover(self, media_type, **kw):
            asked.append((media_type, kw))
            if kw.get("sort_by") != "vote_count.desc":
                return []
            base = 300 if media_type == "movie" else 400
            page = kw.get("page", 1)
            return [_item(base + 20 * page + n, f"{'Film' if media_type == 'movie' else 'Série'} {chr(65 + n)}{page}", media_type)
                    | {"vote_count": 4000, "vote_average": 7.6, "release_date": recent} for n in range(8)]

    db.add(MediaState(tmdb_id=1, media_type="movie", title="A", liked=True))
    db.commit()
    mine = [_item(100 + n, f"Pour moi {chr(65 + n)}") | {"vote_count": 2000, "vote_average": 7.5, "release_date": "2021-03-01"} for n in range(3)]
    ctx = SimpleNamespace(db=db, user=db.get(User, 1), tmdb=WithReleases({("movie", 1): mine}), trakt=None, platforms=[])
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    out = asyncio.run(sg.suggestions(ctx, "all", limit=12))
    releases = [i for i in out if i["reason_key"] == "Sortie récente remarquée"]
    assert len([i for i in releases if i["media_type"] == "movie"]) == sg.PER_SEED
    assert len([i for i in releases if i["media_type"] == "tv"]) == sg.PER_SEED
    assert {i["title"] for i in out} >= {"Pour moi A", "Pour moi B", "Pour moi C"}  # les suggestions personnelles restent
    window = next(kw for mt, kw in asked if mt == "movie" and kw.get("sort_by") == "vote_count.desc")
    assert window["primary_release_date.lte"] == utcnow().date().isoformat() and window["primary_release_date.gte"] < window["primary_release_date.lte"]


def test_references_cover_more_than_the_strongest_titles(db):
    """Références : les 20 plus fortes, plus un tirage du jour parmi les suivantes (vivier de candidats assez large)."""
    db.add_all([MediaState(tmdb_id=n, media_type="movie", title=f"T{n}", liked=n <= 30, watchlist_sources='["local"]') for n in range(1, 101)])
    db.commit()
    seeds, _ = sg.seeds(SimpleNamespace(db=db, user=db.get(User, 1)), ["movie"])
    ids = [s["tmdb_id"] for s in seeds]
    assert len(ids) == len(set(ids)) == sg.SEEDS_TOP + sg.SEEDS_ROTATING == 40
    assert all(i <= 30 for i in ids[:20])  # les plus fortes d'abord (coups de cœur)


def _raw(director=None, genres=(), cast=(), lang="en", year="2015", creator=None):
    crew = [{"id": director[0], "name": director[1], "job": "Director"}] if director else []
    return {"genres": [{"id": g} for g in genres], "keywords": {"keywords": []}, "original_language": lang, "release_date": f"{year}-01-01",
            "credits": {"crew": crew, "cast": [{"id": c[0], "name": c[1]} for c in cast]},
            "created_by": [{"id": creator[0], "name": creator[1]}] if creator else []}


def test_taste_profile_ranks_and_explains(db, monkeypatch):
    villeneuve, horror, scifi = (525, "Denis Villeneuve"), 27, 878
    liked = [(1, "Premier"), (2, "Deuxième"), (3, "Troisième"), (4, "Quatrième"), (5, "Cinquième")]
    db.add_all([MediaState(tmdb_id=i, media_type="movie", title=t, rating=10, watched_sources='["trakt"]') for i, t in liked])
    db.add(MediaState(tmdb_id=9, media_type="movie", title="Horreur ratée", rating=2, watched_sources='["trakt"]'))
    db.commit()
    raw = {("movie", i): _raw(villeneuve if i <= 2 else None, genres=(scifi,)) for i, _ in liked}
    raw[("movie", 9)] = _raw(genres=(horror,))
    raw[("movie", 100)] = _raw(genres=(horror,))  # genre rejeté
    raw[("movie", 101)] = _raw(villeneuve, genres=(scifi,))  # réalisateur aimé
    raw[("movie", 102)] = _raw(genres=(scifi,))
    recs = {("movie", 1): [_item(100, "Cri"), _item(102, "Neutre"), _item(101, "Arrival")]}
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    ctx = _ctx(db, recs)
    ctx.tmdb.raw = raw
    out = asyncio.run(sg.suggestions(ctx, "movie", limit=3))
    assert [i["title"] for i in out] == ["Arrival", "Neutre", "Cri"]  # réalisateur aimé devant, genre rejeté derrière
    assert out[0]["reason_key"] == "Réalisé par {name}, que tu aimes" and out[0]["reason_params"] == {"name": "Denis Villeneuve"}
    assert out[0]["reason"] == "Réalisé par Denis Villeneuve, que tu aimes"
    assert out[1]["reason_key"] == "Parce que tu as aimé {title}" and out[1]["reason_params"]["title"]


def test_more_or_less_like_this(db, monkeypatch):
    from app.models import SuggestionFeedback

    db.add_all([SuggestionFeedback(media_type="movie", tmdb_id=50, title="Plus", value=1), SuggestionFeedback(media_type="movie", tmdb_id=60, title="Moins", value=-1)])
    db.commit()
    pos, neg = sg.signals(_ctx(db, {}), ["movie"])
    assert ("movie", 50) in {(s["media_type"], s["tmdb_id"]) for s in pos} and ("movie", 60) in {(s["media_type"], s["tmdb_id"]) for s in neg}
    recs = {("movie", 50): [_item(60, "Moins"), _item(70, "Voisin")]}
    monkeypatch.setattr(sg, "enrich", _fake_enrich(set()))
    out = asyncio.run(sg.suggestions(_ctx(db, recs), "movie", limit=5))
    assert [i["title"] for i in out] == ["Voisin"]  # les titres déjà jugés ne sont plus proposés


def test_feedback_endpoint_is_per_account(fresh):  # noqa: F811

    admin = client()
    setup_admin(admin)
    alice = member(admin, "alice")
    body = {"media_type": "movie", "tmdb_id": 603, "title": "Matrix", "value": 1}
    assert alice.post("/api/media/suggestions/feedback", json=body).status_code == 200
    assert alice.post("/api/media/suggestions/feedback", json={**body, "value": 2}).status_code == 422
    from app.database import SessionLocal
    from app.models import SuggestionFeedback

    with SessionLocal() as db:
        rows = db.query(SuggestionFeedback).execution_options(all_users=True).all()
        assert [(r.tmdb_id, r.value) for r in rows] == [(603, 1)] and rows[0].user_id != 1  # rangé chez Alice
    alice.post("/api/media/suggestions/feedback", json={**body, "value": 0})
    with SessionLocal() as db:
        assert db.query(SuggestionFeedback).execution_options(all_users=True).count() == 0
