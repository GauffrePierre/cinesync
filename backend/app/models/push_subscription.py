from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UserScoped


class PushSubscription(UserScoped, Base):
    """Appareil abonné aux notifications push (navigateur ou PWA installée) d'un compte."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "endpoint", name="uq_push_endpoint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text)  # adresse du service push du navigateur (liste blanche)
    p256dh: Mapped[str] = mapped_column(String(200))  # clé publique de l'appareil (chiffrement du contenu)
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
