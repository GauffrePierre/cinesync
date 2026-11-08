"""Clé secrète du serveur (signature des adresses d'images relayées…), créée au premier besoin dans le dossier
des données et lisible seulement par le propriétaire."""

import os
import secrets
from functools import lru_cache

from app.config import config


@lru_cache(maxsize=1)
def server_secret() -> bytes:
    path = config.data_dir / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return bytes.fromhex(path.read_text().strip())
