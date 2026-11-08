"""Lien watch.plex.tv (ouvert par l'app Plex sur iPhone / iPad sur la bonne fiche)."""

import asyncio

from app.services.cache import cache
from app.services.plex_account import PlexAccount


class FakeAccount(PlexAccount):
    def __init__(self, slug):
        super().__init__("token", "client")
        self.slug, self.calls = slug, 0

    async def resolve(self, media_type, tmdb_id):
        return "5d776b" if self.slug else None

    async def _req(self, method, url, **params):
        self.calls += 1
        return {"MediaContainer": {"Metadata": [{"slug": self.slug}]}}


def run(coro):
    return asyncio.run(coro)


def test_movie_show_and_episode_links():
    cache.clear()
    acc = FakeAccount("the-polar-express-2004")
    assert run(acc.watch_url("movie", 5255)) == "https://watch.plex.tv/movie/the-polar-express-2004"
    acc = FakeAccount("andor")
    assert run(acc.watch_url("tv", 83867)) == "https://watch.plex.tv/show/andor"
    assert run(acc.watch_url("tv", 83867, 1, 12)) == "https://watch.plex.tv/show/andor/season/1/episode/12"
    assert acc.calls == 1  # le slug est mis en cache


def test_unknown_title_has_no_link():
    cache.clear()
    assert run(FakeAccount(None).watch_url("movie", 1)) is None
