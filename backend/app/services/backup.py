"""Sauvegardes de la base SQLite (comptes, réglages, jetons des services, historique).

Copie cohérente même pendant l'utilisation (API de sauvegarde de SQLite, compatible WAL), compressée
en gzip dans DATA_DIR/backups, lisible par le seul propriétaire. Une sauvegarde automatique par jour
(réglable par l'administrateur), les plus anciennes au-delà du nombre à garder sont supprimées.

Restauration (conteneur arrêté) : décompresser le fichier à la place de cinesync.db et supprimer
cinesync.db-wal / cinesync.db-shm, puis redémarrer. Voir docs/wiki/11-release-and-deploy.md.
"""

import gzip
import logging
import os
import re
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import config

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^syncine-\d{8}-\d{6}(?:-\d+)?\.db\.gz$")
DEFAULT_KEEP = 7
MAX_KEEP = 60
AUTO_EVERY = 23 * 3600  # sauvegarde automatique si la dernière date de plus de 23 h

last_error: str | None = None  # dernière erreur de sauvegarde automatique (affichée à l'admin)


def backup_dir() -> Path:
    return config.data_dir / "backups"


def _db_path() -> Path:
    return config.data_dir / "cinesync.db"


def _info(p: Path) -> dict:
    st = p.stat()
    return {"name": p.name, "size": st.st_size, "created_at": datetime.fromtimestamp(st.st_mtime, UTC).isoformat()}


def list_backups() -> list[dict]:
    """Sauvegardes, de la plus récente à la plus ancienne."""
    d = backup_dir()
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.is_file() and not p.is_symlink() and NAME_RE.fullmatch(p.name)]
    return [_info(p) for p in sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)]


def path_of(name: str) -> Path | None:
    """Chemin d'une sauvegarde existante, si le nom est bien celui d'une sauvegarde (aucun autre fichier)."""
    if not NAME_RE.fullmatch(name or ""):
        return None
    p = backup_dir() / name
    return p if p.is_file() else None


def create() -> dict:
    """Nouvelle sauvegarde (bloquant : à lancer dans un thread). Renvoie ses informations."""
    d = backup_dir()
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    stem = f"syncine-{datetime.now():%Y%m%d-%H%M%S}"
    name, n = f"{stem}.db.gz", 1
    while (d / name).exists():
        n += 1
        name = f"{stem}-{n}.db.gz"
    raw, part = d / f".{name}.db", d / f".{name}.part"
    try:
        src = sqlite3.connect(_db_path(), timeout=30)
        dst = sqlite3.connect(raw)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(raw, "rb") as f_in, gzip.open(part, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out, 1024 * 1024)
        os.chmod(part, 0o600)
        part.replace(d / name)
    finally:
        raw.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
    return _info(d / name)


def rotate(keep: int) -> int:
    """Ne garde que les `keep` sauvegardes les plus récentes ; renvoie le nombre supprimé."""
    removed = 0
    for item in list_backups()[max(1, keep) :]:
        (backup_dir() / item["name"]).unlink(missing_ok=True)
        removed += 1
    return removed


def delete(name: str) -> bool:
    p = path_of(name)
    if p is None:
        return False
    p.unlink()
    return True


def due() -> bool:
    """Pas de sauvegarde récente (moins de 23 h) ?"""
    items = list_backups()
    if not items:
        return True
    newest = backup_dir() / items[0]["name"]
    return time.time() - newest.stat().st_mtime >= AUTO_EVERY


def run_automatic(enabled: bool, keep: int) -> dict | None:
    """Tâche périodique : sauvegarde si activée et due, puis rotation. Une erreur est gardée pour l'admin."""
    global last_error
    if not enabled or not due():
        return None
    try:
        info = create()
        rotate(keep)
        last_error = None
        log.info("Sauvegarde automatique : %s", info["name"])
        return info
    except (OSError, sqlite3.Error) as e:
        last_error = f"{e.__class__.__name__}: {e}"
        log.error("Sauvegarde automatique impossible : %s", last_error)
        return None
