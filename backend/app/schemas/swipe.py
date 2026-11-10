from typing import Literal

from pydantic import BaseModel, Field


class SwipeIn(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "tv"]
    action: Literal["skip", "seen", "watchlist", "like"]
    rating: float | None = Field(default=None, ge=0.5, le=5, multiple_of=0.5)  # pour "seen", par demi-étoile
    title: str = ""


class SwipeOut(BaseModel):
    ok: bool
    trakt_synced: bool
    message: str | None = None
