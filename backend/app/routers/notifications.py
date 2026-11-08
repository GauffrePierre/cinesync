"""Notifications : titres de la watchlist devenus disponibles sur une plateforme active."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update

from app.models import Notification
from app.services.context import Ctx, get_ctx

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(limit: int = 50, ctx: Ctx = Depends(get_ctx)):
    rows = ctx.db.execute(select(Notification).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).scalars()
    unread = ctx.db.execute(select(func.count()).select_from(Notification).where(Notification.read.is_(False))).scalar_one()
    return {"results": [r.to_dict() for r in rows], "unread": unread}


@router.post("/read-all")
def read_all(ctx: Ctx = Depends(get_ctx)):
    ctx.db.execute(update(Notification).values(read=True))
    ctx.db.commit()
    return {"ok": True}


@router.post("/check")
async def check_now(ctx: Ctx = Depends(get_ctx)):
    """Lance immédiatement la vérification pour ce compte (normalement toutes les 24 h)."""
    from app.scheduler import availability_one, episodes_one

    availability = await availability_one(ctx)
    episodes = await episodes_one(ctx)
    return {
        "checked": availability.get("checked", 0),
        "created": availability.get("created", 0) + episodes.get("created", 0),
        "episodes_checked": episodes.get("checked", 0),
        **({"skipped": availability["skipped"]} if availability.get("skipped") and not episodes.get("created") else {}),
    }


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, ctx: Ctx = Depends(get_ctx)):
    n = ctx.db.get(Notification, notification_id)
    if n is None or n.user_id != ctx.user.id:
        raise HTTPException(404, "Notification introuvable")
    n.read = True
    ctx.db.commit()
    return {"ok": True}


@router.delete("/{notification_id}")
def remove(notification_id: int, ctx: Ctx = Depends(get_ctx)):
    n = ctx.db.get(Notification, notification_id)
    if n is not None and n.user_id == ctx.user.id:
        ctx.db.delete(n)
        ctx.db.commit()
    return {"ok": True}
