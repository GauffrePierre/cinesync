from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped

REQUEST_STATUSES = ("pending", "sent", "declined", "available")


class MediaRequest(UserScoped, Base):
    """Demande d'ajout d'un titre à la bibliothèque Plex.

    - Seerr connecté : envoyée tout de suite à Seerr (statut « sent »), validée ensuite dans Seerr.
    - Sans Seerr : reste « pending » ; l'administrateur la traite depuis CinéSync.
    """

    __tablename__ = "media_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, index=True)
    media_type: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_by: Mapped[str] = mapped_column(String, default="admin")  # identifiant de compte (multi-comptes à venir)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    seerr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type,
            "title": self.title,
            "year": self.year,
            "poster": self.poster,
            "requested_by": self.requested_by,
            "user_id": self.user_id,
            "status": self.status,
            "seerr_url": self.seerr_url,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
