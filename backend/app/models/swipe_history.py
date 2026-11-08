from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped

SWIPE_ACTIONS = ("skip", "seen", "watchlist", "like")


class SwipeHistory(UserScoped, Base):
    """Mémoire du mode swipe : un titre swipé n'est plus jamais reproposé."""

    __tablename__ = "swipe_history"
    __table_args__ = (UniqueConstraint("user_id", "tmdb_id", "media_type", name="uq_swipe_media"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, index=True)
    media_type: Mapped[str] = mapped_column(String(8))  # "movie" | "tv"
    action: Mapped[str] = mapped_column(String(16))  # skip | seen | watchlist | like
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 étoiles si "seen"
    title: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
