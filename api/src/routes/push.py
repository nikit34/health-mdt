"""Web Push subscription management + VAPID public key endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth_deps import get_current_user
from ..config import get_settings
from ..db import PushSubscription, User
from ..db.session import get_session

router = APIRouter()


@router.get("/vapid-key")
def get_vapid_key() -> dict:
    """Return the VAPID public key so the browser can subscribe."""
    s = get_settings()
    if not s.has_vapid:
        raise HTTPException(400, "Web Push not configured (VAPID keys missing)")
    return {"public_key": s.vapid_public_key}


class SubscribeIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""


@router.post("/subscribe")
def subscribe(
    payload: SubscribeIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Register a push subscription for the current user's browser."""
    s = get_settings()
    if not s.has_vapid:
        raise HTTPException(400, "Web Push not configured")

    # Deduplicate by endpoint
    existing = session.exec(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == payload.endpoint,
        )
    ).first()
    if existing:
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.user_agent = payload.user_agent
        session.add(existing)
    else:
        sub = PushSubscription(
            user_id=user.id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh,
            auth=payload.auth,
            user_agent=payload.user_agent,
        )
        session.add(sub)

    user.push_notifications = True
    session.add(user)
    session.commit()
    return {"ok": True}


@router.delete("/subscribe")
def unsubscribe(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Remove all push subscriptions for the current user."""
    subs = session.exec(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    ).all()
    for s in subs:
        session.delete(s)
    user.push_notifications = False
    session.add(user)
    session.commit()
    return {"ok": True}


@router.get("/status")
def push_status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Return current push subscription status."""
    count = len(session.exec(
        select(PushSubscription.id).where(PushSubscription.user_id == user.id)
    ).all())
    return {
        "enabled": user.push_notifications,
        "subscriptions": count,
    }
