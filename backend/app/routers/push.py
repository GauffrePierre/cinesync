"""Notifications push : abonnement de cet appareil, désabonnement, essai."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.models import PushSubscription
from app.services import push
from app.services.context import Ctx, get_ctx
from app.services.messages import render

router = APIRouter(prefix="/push", tags=["push"])

MAX_DEVICES = 10  # appareils abonnés par compte


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.get("/config")
def config(ctx: Ctx = Depends(get_ctx)):
    devices = ctx.db.execute(select(PushSubscription.id)).all()
    return {"public_key": push.public_key(), "devices": len(devices)}


@router.post("/subscribe")
def subscribe(body: SubscriptionIn, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Abonne cet appareil au compte connecté. Un appareil ne reçoit que les notifications d'un seul compte :
    s'il était abonné pour un autre compte (changement d'utilisateur), il passe à celui-ci."""
    if not push.allowed_endpoint(body.endpoint):
        raise HTTPException(422, "Service de notification non reconnu")
    ctx.db.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint).execution_options(all_users=True))
    mine = ctx.db.execute(select(PushSubscription).order_by(PushSubscription.created_at)).scalars().all()
    for old in mine[: max(0, len(mine) - MAX_DEVICES + 1)]:  # le plus ancien laisse sa place
        ctx.db.delete(old)
    ctx.db.add(PushSubscription(
        endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth, user_agent=(request.headers.get("user-agent") or "")[:200],
    ))
    ctx.db.commit()
    return {"ok": True}


@router.post("/unsubscribe")
def unsubscribe(body: EndpointIn, ctx: Ctx = Depends(get_ctx)):
    ctx.db.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    ctx.db.commit()
    return {"ok": True}


@router.post("/test")
async def test(body: EndpointIn, ctx: Ctx = Depends(get_ctx)):
    """Notification d'essai sur cet appareil."""
    sub = ctx.db.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Cet appareil n'est pas abonné")
    lang = ctx.settings.ui_language or "fr"
    payload = {"title": "SynCiné", "body": render("Notifications activées sur cet appareil", {}, lang), "url": "/profile", "tag": "syncine-test"}

    def go() -> int:
        import httpx

        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            return push.send(sub, payload, client)

    try:
        status = await asyncio.to_thread(go)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, "Service de notification injoignable") from e
    if status in (404, 410):
        ctx.db.delete(sub)
        ctx.db.commit()
        raise HTTPException(410, "Abonnement expiré : réactive les notifications")
    if status >= 300:
        raise HTTPException(502, f"Le service de notification a répondu {status}")
    return {"ok": True}
