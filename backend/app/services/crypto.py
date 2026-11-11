"""Chiffrement au repos des jetons et des clés gardés dans la base (Plex, Jellyfin, Trakt, TMDB, Seerr, 2FA…).

La base et ses sauvegardes ne contiennent que des valeurs chiffrées (AES-256-GCM) avec une clé dérivée de la clé du
serveur (`data/secret.key`, jamais copiée dans une sauvegarde) : un fichier de sauvegarde qui s'égare ne donne plus
accès aux services. Contrepartie voulue : une base restaurée sans cette clé démarre avec les services déconnectés
(et la double authentification à réactiver).

Une colonne `EncryptedString` ne peut pas servir dans un filtre SQL (le chiffré change à chaque écriture).
"""

import base64
import binascii
import hashlib
import logging
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.services.secret import server_secret

log = logging.getLogger(__name__)

PREFIX = "enc1:"  # version du format : une valeur sans ce préfixe est une valeur en clair d'avant le chiffrement
_warned = False


@lru_cache(maxsize=1)
def _aead() -> AESGCM:
    return AESGCM(hashlib.sha256(b"syncine-db-v1|" + server_secret()).digest())


def encrypt(value: str) -> str:
    nonce = os.urandom(12)
    return PREFIX + base64.b64encode(nonce + _aead().encrypt(nonce, value.encode(), None)).decode()


def decrypt(stored: str) -> str:
    """Valeur en clair ; chaîne vide si la clé du serveur n'est pas celle qui a chiffré (base restaurée ailleurs)."""
    global _warned
    if not stored.startswith(PREFIX):
        return stored  # pas encore chiffrée (migration au démarrage)
    try:
        raw = base64.b64decode(stored[len(PREFIX):], validate=True)
        return _aead().decrypt(raw[:12], raw[12:], None).decode()
    except (InvalidTag, ValueError, binascii.Error):
        if not _warned:
            _warned = True
            log.warning("Jetons illisibles : la base a été chiffrée avec une autre clé de serveur (secret.key). "
                        "Les services concernés sont à reconnecter, la double authentification à réactiver.")
        return ""


class EncryptedString(TypeDecorator):
    """Colonne de texte chiffrée dans la base, en clair dans le code."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value) if value else value

    def process_result_value(self, value, dialect):
        return decrypt(value) if value else value
