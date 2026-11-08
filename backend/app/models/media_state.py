import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


def _load(v: str | None) -> list:
    try:
        return json.loads(v or "[]")
    except (ValueError, TypeError):
        return []


class MediaState(UserScoped, Base):
    """État personnel d'un titre, fusionné depuis tous les services (Trakt, Plex, Letterboxd, CinéSync).

    C'est aussi la sauvegarde locale : tout ce qui est fait dans CinéSync y est enregistré,
    en plus d'être envoyé à chaque service qui sait le stocker.
    Les listes *_sources indiquent où l'information a été trouvée : "trakt", "plex", "letterboxd", "local".
    """

    __tablename__ = "media_state"
    __table_args__ = (UniqueConstraint("user_id", "tmdb_id", "media_type", name="uq_media_state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, index=True)
    media_type: Mapped[str] = mapped_column(String(8))
    title: Mapped[str] = mapped_column(String, default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster: Mapped[str | None] = mapped_column(String, nullable=True)

    watchlist_sources: Mapped[str] = mapped_column(Text, default="[]")
    watched_sources: Mapped[str] = mapped_column(Text, default="[]")
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # sur 10
    rating_source: Mapped[str] = mapped_column(String(16), default="")
    liked: Mapped[bool] = mapped_column(Boolean, default=False)
    disliked: Mapped[bool] = mapped_column(Boolean, default=False)  # « pas intéressé » : exclu des suggestions
    listed_at: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO
    watched_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # Disponibilités (mises à jour par la vérification quotidienne) et notifications déjà envoyées
    providers: Mapped[str] = mapped_column(Text, default="[]")
    providers_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notified_platforms: Mapped[str] = mapped_column(Text, default="[]")
    # Premier passage de la vérification des disponibilités : sert de référence (aucune alerte)
    availability_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # --- accès pratiques ---------------------------------------------------------

    def sources(self, field: str) -> set[str]:
        return set(_load(getattr(self, f"{field}_sources")))

    def set_sources(self, field: str, values: set[str]) -> None:
        setattr(self, f"{field}_sources", json.dumps(sorted(values)))

    def add_source(self, field: str, source: str) -> None:
        self.set_sources(field, self.sources(field) | {source})

    def remove_source(self, field: str, source: str) -> None:
        self.set_sources(field, self.sources(field) - {source})

    @property
    def in_watchlist(self) -> bool:
        return bool(self.sources("watchlist"))

    @property
    def watched(self) -> bool:
        return bool(self.sources("watched"))

    def state(self) -> dict:
        return {
            "in_watchlist": self.in_watchlist,
            "watchlist_sources": sorted(self.sources("watchlist")),
            "watched": self.watched,
            "watched_sources": sorted(self.sources("watched")),
            "rating": self.rating,
            "rating_source": self.rating_source or None,
            "liked": self.liked,
            "disliked": self.disliked,
            "listed_at": self.listed_at,
            "watched_at": self.watched_at,
        }

    def to_item(self) -> dict:
        return {
            "id": self.tmdb_id,
            "media_type": self.media_type,
            "title": self.title,
            "year": self.year,
            "poster": self.poster,
            "providers": _load(self.providers),
            **self.state(),
        }
