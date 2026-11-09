import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models import UserSettings

SECRET_FIELDS = ("tmdb_api_key", "plex_token", "trakt_client_secret", "seerr_api_key", "youtube_api_key", "jellyfin_api_key")


def _nav_order(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [k for k in value if isinstance(k, str)] if isinstance(value, list) else []


def mask(value: str) -> str | None:
    if not value:
        return None
    return "••••" + value[-4:] if len(value) > 8 else "••••"


class SettingsOut(BaseModel):
    language: str
    plex_url: str
    plex_server_name: str
    plex_machine_id: str
    plex_account_connected: bool
    trakt_client_id: str
    trakt_username: str
    trakt_connected: bool
    seerr_url: str
    letterboxd_username: str
    justwatch_enabled: bool
    cinemas: list[dict]
    cinema_films_only: bool
    auto_sync: bool
    hide_seen: bool
    share_watchlist: bool
    recent_days: int
    onboarding: str
    nav_order: list[str]
    notify_availability: bool
    notify_new_episodes: bool
    notify_services: bool
    notify_episode_via: list[str]
    notify_movie_via: list[str]
    country_code: str
    active_platforms: list[int]
    theme: str
    ui_language: str
    # Les secrets ne sont jamais renvoyés en clair : seulement un aperçu masqué (ou null)
    secrets: dict[str, str | None]

    @classmethod
    def from_model(cls, s: UserSettings, admin: bool = True, has_plex: bool = True) -> "SettingsOut":
        return cls(
            language=s.language,
            plex_url=s.plex_url if admin else "",
            # Serveur Plex de l'admin : invisible pour un membre sans Plex
            plex_server_name=s.plex_server_name if has_plex else "",
            plex_machine_id=s.plex_machine_id if has_plex else "",
            plex_account_connected=bool(s.plex_account_token),
            trakt_client_id=s.trakt_client_id,
            trakt_username=s.trakt_username,
            trakt_connected=bool(s.trakt_access_token),
            seerr_url=s.seerr_url if admin else "",
            letterboxd_username=s.letterboxd_username,
            justwatch_enabled=s.justwatch_enabled,
            cinemas=s.cinema_list,
            cinema_films_only=s.cinema_films_only,
            auto_sync=s.auto_sync,
            hide_seen=s.hide_seen,
            share_watchlist=s.share_watchlist,
            recent_days=s.recent_days,
            onboarding=s.onboarding or "done",
            nav_order=_nav_order(s.nav_order),
            notify_availability=s.notify_availability,
            notify_new_episodes=s.notify_new_episodes,
            notify_services=s.notify_services,
            notify_episode_via=s.episode_via,
            notify_movie_via=s.movie_via,
            country_code=s.country_code,
            active_platforms=s.platforms,
            theme=s.theme,
            ui_language=s.ui_language or "fr",
            # Un membre voit seulement si les clés du serveur existent, jamais leur aperçu
            secrets={f: mask(getattr(s, f)) if admin else ("••••" if getattr(s, f) else None) for f in SECRET_FIELDS},
        )


class SettingsUpdate(BaseModel):
    """Tous les champs sont optionnels : seuls ceux envoyés sont modifiés. Une chaîne vide efface."""

    tmdb_api_key: str | None = None
    language: str | None = None
    plex_url: str | None = None
    plex_token: str | None = None
    trakt_client_id: str | None = None
    trakt_client_secret: str | None = None
    seerr_url: str | None = None
    seerr_api_key: str | None = None
    letterboxd_username: str | None = None
    justwatch_enabled: bool | None = None
    cinemas: list[dict] | None = None
    cinema_films_only: bool | None = None
    auto_sync: bool | None = None
    hide_seen: bool | None = None
    share_watchlist: bool | None = None
    recent_days: int | None = Field(default=None, ge=0, le=365)
    onboarding: Literal["pending", "done"] | None = None
    nav_order: list[Annotated[str, StringConstraints(pattern=r"^[a-z]{2,20}$")]] | None = Field(default=None, max_length=30)
    notify_availability: bool | None = None
    notify_new_episodes: bool | None = None
    notify_services: bool | None = None
    notify_episode_via: list[Literal["air", "platforms", "plex"]] | None = Field(default=None, max_length=3)
    notify_movie_via: list[Literal["platforms", "plex"]] | None = Field(default=None, max_length=2)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    active_platforms: list[int] | None = None
    theme: Literal["auto", "light", "dark"] | None = None
    ui_language: Literal["fr", "en", "it", "de", "es"] | None = None
    youtube_api_key: str | None = None


class TestResult(BaseModel):
    ok: bool
    message: str
    details: dict | None = None
