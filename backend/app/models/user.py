from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ROLES = ("admin", "member")


class User(Base):
    """Un compte SynCiné : l'administrateur ou un membre de la famille.

    Connexion : mot de passe local (choisi par l'admin, à changer à la première connexion)
    ou compte Plex, si l'admin l'a autorisé parmi les comptes ayant accès à son serveur.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)  # identifiant de connexion (minuscules)
    display_name: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String(8), default="member")
    password_hash: Mapped[str] = mapped_column(String, default="")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)

    # Compte Plex autorisé (identifiant plex.tv) et son identifiant dans l'historique du serveur
    plex_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    plex_username: Mapped[str] = mapped_column(String, default="")
    plex_thumb: Mapped[str] = mapped_column(String, default="")
    plex_server_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Double authentification (TOTP) : secret actif, secret en cours d'activation, dernier code accepté
    # (refus du rejeu), empreintes des codes de secours (JSON)
    totp_secret: Mapped[str] = mapped_column(String, default="")
    totp_pending: Mapped[str] = mapped_column(String, default="")
    totp_last_counter: Mapped[int] = mapped_column(Integer, default=0)
    recovery_codes: Mapped[str] = mapped_column(Text, default="[]")
    # Codes incorrects d'affilée et blocage temporaire (contre la recherche du code par essais)
    totp_failures: Mapped[int] = mapped_column(Integer, default=0)
    totp_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Demandes envoyées directement à Seerr (sinon : file d'attente de l'admin)
    can_request_direct: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def name(self) -> str:
        return self.display_name or self.plex_username or self.username

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "display_name": self.display_name,
            "role": self.role,
            "is_admin": self.is_admin,
            "has_password": bool(self.password_hash),
            "must_change_password": self.must_change_password,
            "two_factor": bool(self.totp_secret),
            "plex": {"id": self.plex_user_id, "username": self.plex_username, "thumb": self.plex_thumb or None} if self.plex_user_id else None,
            "can_request_direct": self.is_admin or self.can_request_direct,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


class AuthSession(Base):
    """Session de connexion (cookie). Seule l'empreinte SHA-256 du jeton est stockée."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user_agent: Mapped[str] = mapped_column(String, default="")
