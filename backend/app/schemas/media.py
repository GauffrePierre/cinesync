"""Formats communs renvoyés au frontend, quelle que soit la source (TMDB, Plex, Trakt).

Les routers renvoient des dicts conformes à ces modèles ; ils servent de référence
et de documentation OpenAPI.
"""

from typing import Literal

from pydantic import BaseModel

MediaType = Literal["movie", "tv"]


class Provider(BaseModel):
    id: int
    name: str
    logo: str | None = None
    url: str | None = None  # lien direct (JustWatch) si disponible
    type: str | None = None  # flatrate | free | ads | rent | buy


class MediaItem(BaseModel):
    id: int  # identifiant TMDB
    media_type: MediaType
    title: str
    original_title: str | None = None
    overview: str = ""
    poster: str | None = None
    backdrop: str | None = None
    release_date: str | None = None
    year: int | None = None
    vote_average: float = 0
    vote_count: int = 0
    genre_ids: list[int] = []
    providers: list[Provider] = []
    in_plex: bool = False


class MediaRef(BaseModel):
    tmdb_id: int
    media_type: MediaType

