"""Demandes d'ajout à la bibliothèque Plex.

- Admin, ou membre autorisé par l'admin, avec Seerr connecté : envoyée directement à Seerr.
- Sinon : file d'attente, traitée par l'administrateur dans CinéSync (onglet Demandes).
Chaque membre voit ses demandes ; l'admin les voit toutes.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.models import MediaRequest, Notification, User
from app.services.context import Ctx, get_ctx
from app.services.errors import NotConfigured, ServiceError

router = APIRouter(prefix="/requests", tags=["requests"])

OPEN = ("pending", "sent")


class RequestIn(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "tv"]
    title: str = ""
    year: int | None = None
    poster: str | None = None
    seasons: list[int] | None = None
    note: str = ""


class RequestUpdate(BaseModel):
    status: Literal["pending", "declined", "available"]
    note: str | None = None


def find_open(ctx: Ctx, media_type: str, tmdb_id: int) -> MediaRequest | None:
    """Demande en cours pour ce titre, quel que soit le compte (pas de doublon dans la file)."""
    return ctx.db.execute(
        select(MediaRequest)
        .where(MediaRequest.tmdb_id == tmdb_id, MediaRequest.media_type == media_type, MediaRequest.status.in_(OPEN))
        .order_by(MediaRequest.id)
        .limit(1)
        .execution_options(all_users=True)
    ).scalar_one_or_none()


def visible(ctx: Ctx, req: MediaRequest | None) -> dict | None:
    """Demande telle qu'un compte peut la voir : en entier si c'est la sienne (ou pour l'admin),
    sinon seulement son état (« déjà demandé »), sans la note ni le nom de l'autre membre."""
    if req is None:
        return None
    if ctx.is_admin or req.user_id == ctx.user.id:
        return req.to_dict()
    return {"id": None, "tmdb_id": req.tmdb_id, "media_type": req.media_type, "status": req.status, "mine": False}


def _get(ctx: Ctx, request_id: int, admin: bool = True) -> MediaRequest:
    # db.get passe aussi par le filtre par compte : l'admin doit pouvoir lire les demandes de tous
    req = ctx.db.get(MediaRequest, request_id, execution_options={"all_users": ctx.is_admin})
    if req is None or (req.user_id != ctx.user.id and not ctx.is_admin):
        raise HTTPException(404, "Demande introuvable")
    if admin and not ctx.is_admin:
        raise HTTPException(403, "Réservé à l'administrateur")
    return req


def _names(ctx: Ctx) -> dict[int, str]:
    return {u.id: u.name for u in ctx.db.query(User).all()}


def _out(req: MediaRequest, names: dict[int, str]) -> dict:
    return {**req.to_dict(), "user_name": names.get(req.user_id, "")}


def can_send_direct(ctx: Ctx) -> bool:
    return ctx.seerr is not None and (ctx.is_admin or ctx.user.can_request_direct)


def _notify(ctx: Ctx, user_id: int, req: MediaRequest, message: str) -> None:
    ctx.db.add(
        Notification(user_id=user_id, kind="request", tmdb_id=req.tmdb_id, media_type=req.media_type, title=req.title, poster=req.poster, message=message)
    )


async def _send(ctx: Ctx, req: MediaRequest, seasons: list[int] | None = None) -> None:
    res = await ctx.seerr.request(req.media_type, req.tmdb_id, seasons)
    req.status = "sent"
    req.seerr_url = res.get("url")


@router.get("")
def list_requests(status: str | None = None, scope: Literal["mine", "all"] = "mine", ctx: Ctx = Depends(get_ctx)):
    if scope == "all" and not ctx.is_admin:
        raise HTTPException(403, "Réservé à l'administrateur")
    q = select(MediaRequest).order_by(MediaRequest.created_at.desc(), MediaRequest.id.desc())
    if status:
        q = q.where(MediaRequest.status == status)
    if scope == "all":
        q = q.execution_options(all_users=True)
    rows = ctx.db.execute(q).scalars().all()
    names = _names(ctx)
    return {
        "results": [_out(r, names) for r in rows],
        "pending": sum(1 for r in rows if r.status == "pending"),
        "seerr": ctx.seerr is not None,
        "direct": can_send_direct(ctx),
        "allowed": can_request(ctx),
    }


def can_request(ctx: Ctx) -> bool:
    """Une demande ajoute un titre au serveur Plex : réservée à l'admin et aux comptes reliés à Plex."""
    return ctx.is_admin or ctx.plex is not None


@router.post("")
async def create_request(body: RequestIn, ctx: Ctx = Depends(get_ctx)):
    if not can_request(ctx):
        raise HTTPException(403, "Les demandes d'ajout sont réservées aux comptes reliés au serveur Plex")
    existing = find_open(ctx, body.media_type, body.tmdb_id)
    if existing:
        return {"request": visible(ctx, existing), "created": False}
    req = MediaRequest(
        tmdb_id=body.tmdb_id, media_type=body.media_type, title=body.title, year=body.year, poster=body.poster, note=body.note,
        requested_by=ctx.user.username, status="pending",
    )
    ctx.db.add(req)
    message = "Demande enregistrée — l'administrateur la traitera"
    if can_send_direct(ctx):
        try:
            await _send(ctx, req, body.seasons)
            message = "Demande envoyée à Seerr"
        except ServiceError as e:
            # On garde la demande en attente plutôt que de la perdre
            message = f"Seerr indisponible ({e.message}) — demande gardée en attente"
    if req.status == "pending" and not ctx.is_admin:
        # Prévient les administrateurs (cloche) qu'une demande attend
        for admin in ctx.db.query(User).filter(User.role == "admin", User.active.is_(True)):
            _notify(ctx, admin.id, req, f"{ctx.user.name} demande « {req.title} »")
    ctx.db.commit()
    return {"request": _out(req, _names(ctx)), "created": True, "message": message}


@router.post("/{request_id}/send")
async def send_to_seerr(request_id: int, ctx: Ctx = Depends(get_ctx)):
    req = _get(ctx, request_id)
    if not ctx.seerr:
        raise NotConfigured("seerr")
    await _send(ctx, req)
    if req.user_id != ctx.user.id:
        _notify(ctx, req.user_id, req, f"Ta demande « {req.title} » a été envoyée à Seerr")
    ctx.db.commit()
    return _out(req, _names(ctx))


@router.patch("/{request_id}")
def update_request(request_id: int, body: RequestUpdate, ctx: Ctx = Depends(get_ctx)):
    req = _get(ctx, request_id)
    changed = req.status != body.status
    req.status = body.status
    if body.note is not None:
        req.note = body.note
    if changed and req.user_id != ctx.user.id and body.status in ("available", "declined"):
        verdict = "est disponible sur Plex" if body.status == "available" else "a été refusée"
        _notify(ctx, req.user_id, req, f"Ta demande « {req.title} » {verdict}")
    ctx.db.commit()
    return _out(req, _names(ctx))


@router.delete("/{request_id}")
def delete_request(request_id: int, ctx: Ctx = Depends(get_ctx)):
    req = _get(ctx, request_id, admin=False)
    if not ctx.is_admin and req.status != "pending":
        raise HTTPException(403, "Seules les demandes en attente peuvent être retirées")
    ctx.db.delete(req)
    ctx.db.commit()
    return {"ok": True}
