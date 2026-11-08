import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSettings(Base):
    """Réglages d'un compte (id = id du compte).

    Les réglages du serveur (TMDB, serveur Plex, Seerr, JustWatch, application Trakt) ne sont lus que
    sur la ligne de l'administrateur principal (id=1) : voir GLOBAL_FIELDS dans services/context.py.
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # TMDB (clé v3 ou jeton de lecture v4)
    tmdb_api_key: Mapped[str] = mapped_column(String, default="")
    language: Mapped[str] = mapped_column(String, default="fr-FR")

    # Plex : URL + token du serveur choisi (saisis à la main, ou obtenus via le compte plex.tv)
    plex_url: Mapped[str] = mapped_column(String, default="")
    plex_token: Mapped[str] = mapped_column(String, default="")
    plex_client_id: Mapped[str] = mapped_column(String, default="")  # identifiant de SynCiné auprès de plex.tv
    plex_account_token: Mapped[str] = mapped_column(String, default="")  # jeton du compte plex.tv
    plex_server_name: Mapped[str] = mapped_column(String, default="")
    plex_machine_id: Mapped[str] = mapped_column(String, default="")

    # Trakt (application à créer sur trakt.tv/oauth/applications)
    trakt_client_id: Mapped[str] = mapped_column(String, default="")
    trakt_client_secret: Mapped[str] = mapped_column(String, default="")  # obsolète chez Trakt, facultatif
    trakt_code_verifier: Mapped[str] = mapped_column(String, default="")  # PKCE, le temps de la connexion
    trakt_access_token: Mapped[str] = mapped_column(String, default="")
    trakt_refresh_token: Mapped[str] = mapped_column(String, default="")
    trakt_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trakt_username: Mapped[str] = mapped_column(String, default="")
    trakt_oauth_state: Mapped[str] = mapped_column(String, default="")
    trakt_redirect_uri: Mapped[str] = mapped_column(String, default="")  # celle utilisée à la connexion

    # Seerr
    seerr_url: Mapped[str] = mapped_column(String, default="")
    seerr_api_key: Mapped[str] = mapped_column(String, default="")

    # Letterboxd (RSS public)
    letterboxd_username: Mapped[str] = mapped_column(String, default="")

    # JustWatch (API non officielle, désactivable)
    justwatch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Cinémas suivis (séances via AlloCiné) : JSON [{id, name, city}]
    cinemas: Mapped[str] = mapped_column(Text, default="[]")
    cinema_films_only: Mapped[bool] = mapped_column(Boolean, default=True)  # masque opéras, ballets, concerts…

    # Notifications (cloche) : chaque type peut être coupé
    notify_availability: Mapped[bool] = mapped_column(Boolean, default=True)  # watchlist dispo sur tes plateformes
    notify_new_episodes: Mapped[bool] = mapped_column(Boolean, default=True)  # nouvel épisode d'une série suivie
    notify_services: Mapped[bool] = mapped_column(Boolean, default=True)  # service en panne

    # Synchronisation automatique des watchlists / vus / notes entre services
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    # Sauvegardes automatiques de la base (réglage du serveur : ligne 1 seulement)
    backup_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    backup_keep: Mapped[int] = mapped_column(Integer, default=7)
    # Découverte : ne plus proposer les films vus ni les séries vues sans nouvel épisode depuis
    hide_seen: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ordre des onglets du menu (version ordinateur) : liste JSON de clés, vide = ordre par défaut
    nav_order: Mapped[str] = mapped_column(Text, default="")
    # Assistant de premier démarrage : "pending" pour un nouveau compte (les comptes existants : "done")
    onboarding: Mapped[str] = mapped_column(String(8), default="done")
    # Sorties récentes de la watchlist mises en avant pendant N jours (0 = désactivé)
    recent_days: Mapped[int] = mapped_column(Integer, default=30)

    # Préférences
    country_code: Mapped[str] = mapped_column(String, default="CH")
    active_platforms: Mapped[str] = mapped_column(Text, default="[]")  # JSON : ids fournisseurs TMDB
    theme: Mapped[str] = mapped_column(String, default="auto")
    ui_language: Mapped[str] = mapped_column(String, default="fr")  # langue de l'interface (fr | en)

    # Actu Ciné : sources choisies, JSON [{id, name, url, kind, home}] (vide = sélection par défaut selon la langue)
    news_sources: Mapped[str] = mapped_column(Text, default="")
    # Clé API YouTube (réglage du serveur, facultatif) : secours quand le flux public d'une chaîne ne répond pas
    youtube_api_key: Mapped[str] = mapped_column(String, default="")

    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    @property
    def cinema_list(self) -> list[dict]:
        try:
            return json.loads(self.cinemas or "[]")
        except (ValueError, TypeError):
            return []

    @property
    def platforms(self) -> list[int]:
        try:
            return [int(p) for p in json.loads(self.active_platforms or "[]")]
        except (ValueError, TypeError):
            return []

    @platforms.setter
    def platforms(self, value: list[int]) -> None:
        self.active_platforms = json.dumps(sorted({int(v) for v in value}))
