"""Prochaine diffusion d'une série : heure exacte TVmaze rapprochée de l'épisode annoncé par TMDB, plateformes."""

import asyncio
from types import SimpleNamespace

from app.routers import media
from app.services import tvmaze

NETFLIX = {"id": 8, "name": "Netflix", "logo": None}
PRIME = {"id": 119, "name": "Amazon Prime Video", "logo": None}


class Tmdb:
    is_mock = False

    def __init__(self, nxt, providers=(NETFLIX, PRIME)):
        self.nxt, self.prov = nxt, list(providers)

    async def detail(self, media_type, tmdb_id):
        return {"next_episode": self.nxt, "imdb_id": "tt1", "tvdb_id": 2, "networks": [{"name": "HBO"}]}

    async def providers(self, media_type, tmdb_id):
        return {"flatrate": self.prov}


def _airing(monkeypatch, nxt, tm, platforms=(8,), providers=(NETFLIX, PRIME)):
    async def fake(imdb, tvdb):
        return tm

    monkeypatch.setattr(tvmaze, "next_episode", fake)
    monkeypatch.setattr(media, "stream_providers", lambda p: p.get("flatrate", []))
    ctx = SimpleNamespace(tmdb=Tmdb(nxt, providers), platforms=list(platforms))
    return asyncio.run(media.tv_airing(1, ctx))["next"]


TM = {"season": 2, "episode": 5, "name": "Cinq", "airstamp": "2026-11-12T02:00:00+00:00", "channel": "Netflix", "url": "https://www.tvmaze.com/shows/1"}
NXT = {"season_number": 2, "episode_number": 5, "name": "Cinq", "air_date": "2026-11-11"}


def test_exact_time_and_my_platforms(monkeypatch):
    n = _airing(monkeypatch, NXT, TM)
    assert (n["season"], n["episode"], n["airstamp"], n["air_date"]) == (2, 5, TM["airstamp"], "2026-11-12")
    assert [p["name"] for p in n["platforms"]] == ["Netflix"] and n["source_url"] == TM["url"]  # seulement mes plateformes


def test_time_matched_by_date_when_numbering_differs(monkeypatch):
    same_day = _airing(monkeypatch, {**NXT, "air_date": "2026-11-12"}, {**TM, "season": 2026, "episode": 180})
    assert same_day["airstamp"] == TM["airstamp"] and (same_day["season"], same_day["episode"]) == (2, 5)  # numérotation TMDB gardée
    next_day = _airing(monkeypatch, NXT, {**TM, "season": 2026, "episode": 180})
    assert next_day["airstamp"] is None and next_day["source_url"] is None  # sans doute un autre épisode : pas d'heure inventée
    assert next_day["channel"] == "HBO"  # diffuseur TMDB, pas celui d'un épisode non rapproché


def test_same_season_tvmaze_is_more_recent(monkeypatch):
    # TMDB annonce l'épisode 5 (sorti aujourd'hui), TVmaze déjà le 6 : c'est le 6 qui est affiché, avec son heure
    n = _airing(monkeypatch, NXT, {**TM, "episode": 6, "name": "Six", "airstamp": "2026-11-13T02:00:00+00:00"})
    assert (n["episode"], n["name"], n["air_date"], n["airstamp"]) == (6, "Six", "2026-11-13", "2026-11-13T02:00:00+00:00")
    generic = _airing(monkeypatch, NXT, {**TM, "episode": 6, "name": "Episode 6"})
    assert generic["name"] == ""  # titre générique de TVmaze : pas repris
    assert _airing(monkeypatch, {**NXT, "name": "Épisode cinq"}, TM)["name"] == "Épisode cinq"  # même épisode : titre TMDB


def test_tvmaze_only_and_channel_fallback(monkeypatch):
    n = _airing(monkeypatch, None, TM, platforms=(337,))
    assert (n["season"], n["episode"], n["air_date"], n["airstamp"]) == (2, 5, "2026-11-12", TM["airstamp"])
    assert n["platforms"] == [] and n["channel"] == "Netflix"
    assert _airing(monkeypatch, NXT, None)["channel"] == "HBO"  # sans TVmaze : le diffuseur TMDB
    assert _airing(monkeypatch, None, None) is None
