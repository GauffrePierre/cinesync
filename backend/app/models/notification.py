import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


class Notification(UserScoped, Base):
    """Alerte affichée sous la cloche."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="availability")  # availability | service
    service: Mapped[str] = mapped_column(String(16), default="")  # pour kind="service"
    tmdb_id: Mapped[int] = mapped_column(Integer, default=0)
    media_type: Mapped[str] = mapped_column(String(8), default="")
    title: Mapped[str] = mapped_column(String, default="")
    message: Mapped[str] = mapped_column(String, default="")  # texte français (repli)
    # Gabarit (français) et paramètres : traduit dans la langue du compte (services/messages.py)
    msg_key: Mapped[str] = mapped_column(String, default="")
    msg_params: Mapped[str] = mapped_column(Text, default="{}")
    poster: Mapped[str | None] = mapped_column(String, nullable=True)
    platforms: Mapped[str] = mapped_column(Text, default="[]")  # JSON : [{id, name, logo}]
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind or "availability",
            "service": self.service or None,
            "tmdb_id": self.tmdb_id,
            "media_type": self.media_type,
            "title": self.title,
            "message": self.message,
            "msg_key": self.msg_key or None,
            "msg_params": json.loads(self.msg_params or "{}"),
            "poster": self.poster,
            "platforms": json.loads(self.platforms or "[]"),
            "read": self.read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
