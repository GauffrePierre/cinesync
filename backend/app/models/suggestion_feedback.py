from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


class SuggestionFeedback(UserScoped, Base):
    """« Plus comme ça » (+1) ou « Moins comme ça » (-1) sur une suggestion : le titre devient une référence positive
    ou négative pour les suggestions suivantes, et ne t'est plus proposé."""

    __tablename__ = "suggestion_feedback"
    __table_args__ = (UniqueConstraint("user_id", "media_type", "tmdb_id", name="uq_suggestion_feedback"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String(8))
    tmdb_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    value: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
