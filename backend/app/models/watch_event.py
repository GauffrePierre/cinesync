from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


class WatchEvent(UserScoped, Base):
    """Un visionnage daté (film ou épisode), pour les statistiques par jour / semaine / mois / année.

    Sources : historique du serveur Plex (avec le compte Plex qui a regardé), historique Trakt,
    journal Letterboxd, lectures du compte Jellyfin / Emby relié. Les doublons entre sources sont écartés à l'import.
    """

    __tablename__ = "watch_events"
    __table_args__ = (UniqueConstraint("user_id", "source", "source_key", name="uq_watch_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # plex | trakt | letterboxd | jellyfin
    source_key: Mapped[str] = mapped_column(String, index=True)
    plex_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8))  # movie | episode
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # film, ou série pour un épisode
    title: Mapped[str] = mapped_column(String, default="")  # titre du film ou de l'épisode
    show_title: Mapped[str] = mapped_column(String, default="")
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watched_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    runtime_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    genres: Mapped[str] = mapped_column(Text, default="[]")  # JSON : noms de genres
    # Date inconnue (import en masse sur Trakt) : compte dans les totaux, pas dans la répartition dans le temps
    approx_date: Mapped[bool] = mapped_column(Boolean, default=False)
