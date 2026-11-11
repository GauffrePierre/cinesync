"""Espace administrateur : sauvegardes de la base (liste, réglages, sauvegarde immédiate, téléchargement).
Réservé aux administrateurs complets (Ctx.server_admin)."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import backup
from app.services.auth import require_admin
from app.services.context import SHARED_ID, Ctx, get_ctx, require_server_admin, settings_for

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# --- Sauvegardes de la base ----------------------------------------------------------------


class BackupSettings(BaseModel):
    enabled: bool | None = None
    keep: int | None = Field(None, ge=1, le=backup.MAX_KEEP)


def _backups(ctx: Ctx) -> dict:
    shared = settings_for(ctx.db, SHARED_ID).shared
    return {
        "enabled": shared.backup_enabled,
        "keep": shared.backup_keep,
        "items": backup.list_backups(),
        "last_error": backup.last_error,
    }


@router.get("/backups", dependencies=[Depends(require_server_admin)])
def list_backups(ctx: Ctx = Depends(get_ctx)):
    return _backups(ctx)


@router.put("/backups/settings", dependencies=[Depends(require_server_admin)])
def backup_settings(body: BackupSettings, ctx: Ctx = Depends(get_ctx)):
    shared = settings_for(ctx.db, SHARED_ID).shared
    if body.enabled is not None:
        shared.backup_enabled = body.enabled
    if body.keep is not None:
        shared.backup_keep = body.keep
    ctx.db.commit()
    backup.rotate(shared.backup_keep)
    return _backups(ctx)


@router.post("/backups", dependencies=[Depends(require_server_admin)])
async def backup_now(ctx: Ctx = Depends(get_ctx)):
    """Sauvegarde immédiate (puis rotation selon le nombre à garder)."""
    try:
        await asyncio.to_thread(backup.create)
    except OSError as e:
        raise HTTPException(500, f"Sauvegarde impossible : {e.strerror or e}") from e
    backup.rotate(settings_for(ctx.db, SHARED_ID).shared.backup_keep)
    return _backups(ctx)


@router.get("/backups/{name}", dependencies=[Depends(require_server_admin)])
def download_backup(name: str):
    """Téléchargement d'une sauvegarde (jetons des services chiffrés avec la clé du serveur, qui n'y figure pas)."""
    path = backup.path_of(name)
    if path is None:
        raise HTTPException(404, "Sauvegarde introuvable")
    return FileResponse(path, media_type="application/gzip", filename=name, headers={"Cache-Control": "no-store"})


@router.delete("/backups/{name}", dependencies=[Depends(require_server_admin)])
def delete_backup(name: str, ctx: Ctx = Depends(get_ctx)):
    if not backup.delete(name):
        raise HTTPException(404, "Sauvegarde introuvable")
    return _backups(ctx)
