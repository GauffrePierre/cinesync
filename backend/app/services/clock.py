"""Heure courante en UTC, sans fuseau : le format des colonnes DateTime de la base (remplace datetime.utcnow,
obsolète depuis Python 3.12)."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
