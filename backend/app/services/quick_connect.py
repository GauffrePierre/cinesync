"""Demandes Quick Connect en attente (Jellyfin) : le secret reste ici, le navigateur n'a qu'un identifiant opaque
et le code à saisir dans Jellyfin. Mémoire bornée, durée de vie de 10 minutes (comme côté Jellyfin)."""

import secrets
import time
from dataclasses import dataclass, field

TTL = 600
MAX_PENDING = 500
MAX_PER_IP = 5


@dataclass
class Pending:
    secret: str
    code: str
    device: str  # même appareil pour la demande et l'échange contre un jeton
    purpose: str  # login | link
    ip: str
    user_id: int | None = None  # link : le compte SynCiné qui relie
    created: float = field(default_factory=time.monotonic)


_pending: dict[str, Pending] = {}


def _prune() -> None:
    cutoff = time.monotonic() - TTL
    for k in [k for k, p in _pending.items() if p.created < cutoff]:
        _pending.pop(k, None)


def can_start(ip: str) -> bool:
    _prune()
    return len(_pending) < MAX_PENDING and sum(1 for p in _pending.values() if p.ip == ip) < MAX_PER_IP


def new_device() -> str:
    return secrets.token_urlsafe(12)


def add(p: Pending) -> str:
    key = secrets.token_urlsafe(24)
    _pending[key] = p
    return key


def get(key: str, purpose: str, user_id: int | None = None) -> Pending | None:
    """La demande, si elle existe encore et sert bien à cet usage (et, pour relier, à ce compte)."""
    _prune()
    p = _pending.get(key)
    if p is None or p.purpose != purpose or (purpose == "link" and p.user_id != user_id):
        return None
    return p


def drop(key: str) -> None:
    _pending.pop(key, None)


def clear() -> None:
    _pending.clear()
