from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


class SuggestionShown(UserScoped, Base):
    """Suggestions déjà montrées (Découvrir) : un titre proposé plusieurs fois sans réaction descend dans la liste.
    Une présentation compte au plus une fois toutes les 12 heures (recharger la page ne compte pas)."""

    __tablename__ = "suggestion_shown"
    __table_args__ = (UniqueConstraint("user_id", "media_type", "tmdb_id", name="uq_suggestion_shown"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String(8))
    tmdb_id: Mapped[int] = mapped_column(Integer, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    last_shown: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
