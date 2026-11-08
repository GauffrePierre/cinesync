from typing import Literal

from pydantic import BaseModel, Field


class SwipeIn(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "tv"]
    action: Literal["skip", "seen", "watchlist", "like"]
    rating: int | None = Field(default=None, ge=1, le=5)  # pour "seen"
    title: str = ""


class SwipeOut(BaseModel):
    ok: bool
    trakt_synced: bool
    message: str | None = None
