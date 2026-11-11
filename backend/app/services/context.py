"""Contexte d'une requête : compte connecté, ses réglages et les clients des services configurés.

Réglages : chaque compte a sa ligne UserSettings (id = id du compte). Les réglages du serveur
(GLOBAL_FIELDS : TMDB, serveur Plex, Seerr, JustWatch, application Trakt) sont toujours lus et écrits
sur la ligne de l'administrateur principal (id=1) — ctx.settings fait l'aiguillage.
"""

from dataclasses import dataclass
from functools import cached_property

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import config
from app.database import bind_user, get_db
from app.models import User, UserSettings
from app.services.auth import require_ready
from app.services.errors import NotConfigured
from app.services.justwatch_client import JustWatchClient
from app.services.letterboxd_client import LetterboxdClient
from app.services.mock_data import MockPlex, MockTMDB, MockTrakt
from app.services.jellyfin_client import JellyfinClient
from app.services.plex_account import PlexAccount
from app.services.plex_client import PlexClient
from app.services.seerr_client import SeerrClient
from app.services.tmdb_client import TMDBClient
from app.services.trakt_client import TraktClient


# Réglages partagés par tous les comptes, configurés une fois par l'administrateur
GLOBAL_FIELDS = frozenset({
    "tmdb_api_key", "plex_url", "plex_server_name", "plex_machine_id", "plex_client_id",
    "seerr_url", "seerr_api_key", "justwatch_enabled", "trakt_client_id", "trakt_client_secret", "youtube_api_key",
    "jellyfin_url", "jellyfin_public_url", "jellyfin_api_key", "jellyfin_server_id", "jellyfin_server_name", "jellyfin_kind",
    "admins_full_access",
})
SHARED_ID = 1


class EffectiveSettings:
    """Vue des réglages d'un compte : champs globaux -> ligne partagée, le reste -> ligne du compte."""

    __slots__ = ("_own", "_shared")

    def __init__(self, own: UserSettings, shared: UserSettings):
        object.__setattr__(self, "_own", own)
        object.__setattr__(self, "_shared", shared)

    def __getattr__(self, name):
        return getattr(self._shared if name in GLOBAL_FIELDS else self._own, name)

    def __setattr__(self, name, value):
        setattr(self._shared if name in GLOBAL_FIELDS else self._own, name, value)

    @property
    def own(self) -> UserSettings:
        return self._own

    @property
    def shared(self) -> UserSettings:
        return self._shared


def settings_for(db: Session, user_id: int) -> EffectiveSettings:
    own = db.get(UserSettings, user_id)
    if own is None:
        own = UserSettings(id=user_id, onboarding="pending")  # compte sans réglages : assistant de démarrage
        db.add(own)
        db.commit()
    shared = own if user_id == SHARED_ID else db.get(UserSettings, SHARED_ID)
    return EffectiveSettings(own, shared)


@dataclass
class Ctx:
    db: Session
    settings: EffectiveSettings
    user: User

    @property
    def country(self) -> str:
        return self.settings.country_code or "CH"

    @property
    def platforms(self) -> list[int]:
        return self.settings.platforms

    # Les propriétés renvoient None si le service n'est pas configuré,
    # sauf TMDB qui renvoie un client factice (c'est le cœur de l'appli).

    @cached_property
    def tmdb(self) -> TMDBClient | MockTMDB:
        if self.settings.tmdb_api_key:
            return TMDBClient(self.settings.tmdb_api_key, self.settings.language, self.country)
        return MockTMDB()

    @property
    def is_admin(self) -> bool:
        return self.user.is_admin

    @property
    def server_admin(self) -> bool:
        """Administrateur complet : serveur multimédia avec les accès du serveur (tableau de bord, bibliothèque
        sans compte relié), réglages du serveur, sauvegardes. L'administrateur principal toujours ; les autres
        seulement s'il le leur laisse (réglage admins_full_access), sinon ils gèrent les comptes et les demandes."""
        return self.user.is_admin and (self.user.id == SHARED_ID or bool(self.settings.shared.admins_full_access))

    @cached_property
    def plex(self) -> PlexClient | None:
        """Serveur Plex partagé, en lecture, avec le jeton propre au compte.
        Un administrateur sans jeton propre utilise celui du serveur (voir server_admin). Un membre sans compte Plex
        relié n'a AUCUN accès Plex : ni bibliothèque, ni badges, ni nom du serveur (rien du Plex de l'admin)."""
        token = self.settings.own.plex_token or (self.settings.shared.plex_token if self.server_admin else "")
        if self.settings.plex_url and token:
            return PlexClient(self.settings.plex_url, token)
        return None

    @cached_property
    def plex_own(self) -> PlexClient | None:
        """Serveur Plex avec le jeton propre au compte : vus, notes, lectures — jamais ceux d'un autre."""
        if self.settings.plex_url and self.settings.own.plex_token:
            return PlexClient(self.settings.plex_url, self.settings.own.plex_token)
        return None

    @cached_property
    def plex_admin(self) -> PlexClient | None:
        """Serveur Plex avec le jeton de l'administrateur (historique complet, sessions, analyses)."""
        if self.settings.plex_url and self.settings.shared.plex_token:
            return PlexClient(self.settings.plex_url, self.settings.shared.plex_token)
        return None

    @cached_property
    def plex_account(self) -> PlexAccount | None:
        """Compte plex.tv (watchlist, vu, notes) — disponible après « Se connecter avec Plex »."""
        if self.settings.plex_account_token and self.settings.plex_client_id:
            return PlexAccount(self.settings.plex_account_token, self.settings.plex_client_id)
        return None

    @cached_property
    def trakt(self) -> TraktClient | None:
        """Client Trakt connecté (token OAuth présent), sinon None."""
        if self.settings.trakt_client_id and self.settings.trakt_access_token:
            return TraktClient(self.settings, self.db)
        return None

    @cached_property
    def trakt_app(self) -> TraktClient | None:
        """Client Trakt sans exigence de connexion (OAuth, recherche publique)."""
        if self.settings.trakt_client_id:
            return TraktClient(self.settings, self.db)
        return None

    @cached_property
    def seerr(self) -> SeerrClient | None:
        # Seerr renseigne sur la bibliothèque du serveur : rien pour un membre qui n'y est pas relié
        if not (self.is_admin or self.media is not None):
            return None
        if self.settings.seerr_url and self.settings.seerr_api_key:
            return SeerrClient(self.settings.seerr_url, self.settings.seerr_api_key)
        return None

    @cached_property
    def letterboxd(self) -> LetterboxdClient | None:
        if self.settings.letterboxd_username:
            return LetterboxdClient(self.settings.letterboxd_username)
        return None

    @cached_property
    def justwatch(self) -> JustWatchClient | None:
        if self.settings.justwatch_enabled:
            return JustWatchClient(self.country, self.settings.language)
        return None

    @cached_property
    def jellyfin(self) -> JellyfinClient | None:
        """Serveur Jellyfin / Emby, avec le compte relié de cet utilisateur (ses vus).
        L'administrateur sans compte relié utilise la clé API (bibliothèque, sans état « vu »). Un membre sans
        compte Jellyfin relié n'a aucun accès, comme pour Plex."""
        s = self.settings
        if not s.jellyfin_url:
            return None
        own_token, own_user = s.own.jellyfin_token, s.own.jellyfin_user_id
        if own_token and own_user:
            token, user = own_token, own_user
        elif self.server_admin and s.jellyfin_api_key:
            token, user = s.jellyfin_api_key, ""
        else:
            return None
        return JellyfinClient(s.jellyfin_url, token, user, s.jellyfin_server_id, s.jellyfin_public_url, s.jellyfin_kind)

    @cached_property
    def jellyfin_admin(self) -> JellyfinClient | None:
        """Serveur Jellyfin / Emby avec la clé API de l'administrateur (comptes, lectures en cours)."""
        s = self.settings
        if s.jellyfin_url and s.jellyfin_api_key:
            return JellyfinClient(s.jellyfin_url, s.jellyfin_api_key, "", s.jellyfin_server_id, s.jellyfin_public_url, s.jellyfin_kind)
        return None

    @property
    def media(self) -> "PlexClient | JellyfinClient | None":
        """Serveur multimédia de la bibliothèque : Plex s'il est relié, sinon Jellyfin / Emby."""
        return self.plex or self.jellyfin

    # Versions « toujours disponibles » pour les pages dédiées (données factices sinon)
    @property
    def plex_or_mock(self) -> PlexClient | MockPlex:
        """Bibliothèque Plex, ou démonstration pour l'admin tant que Plex n'est pas relié.
        Un membre sans Plex n'a ni l'une ni l'autre."""
        if self.media is None and not self.user.is_admin:
            raise NotConfigured("plex", "Ce compte n'est pas relié à Plex")
        return self.media or MockPlex()

    @property
    def trakt_or_mock(self) -> TraktClient | MockTrakt:
        return self.trakt or MockTrakt()


def ctx_for(db: Session, user: User) -> Ctx:
    """Contexte d'un compte hors requête (tâches planifiées) : la session est liée à ce compte."""
    bind_user(db, user.id)
    return Ctx(db=db, settings=settings_for(db, user.id), user=user)


def get_ctx(db: Session = Depends(get_db), user: User = Depends(require_ready)) -> Ctx:
    ctx = Ctx(db=db, settings=settings_for(db, user.id), user=user)
    db.commit()  # rend la connexion au pool ; elle est reprise au besoin, le temps d'une requête SQL
    return ctx


def public_base_url(request: Request) -> str:
    """URL publique de l'appli (PUBLIC_URL, sinon déduite des en-têtes du proxy)."""
    if config.public_url:
        return config.public_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def require_server_admin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    """Réglages du serveur, tableau de bord, sauvegardes : administrateur complet seulement (voir Ctx.server_admin)."""
    if not ctx.server_admin:
        raise HTTPException(403, "Réservé à l'administrateur principal")
    return ctx
