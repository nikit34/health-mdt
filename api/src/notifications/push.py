"""Web Push notifications via VAPID.

Sends brief/MDT/task notifications to all subscribed browsers for a user.
Stale subscriptions (410 Gone) are auto-removed.
"""
from __future__ import annotations

import json
import logging

from sqlmodel import Session, select

from ..config import get_settings
from ..db import PushSubscription, User

log = logging.getLogger(__name__)


def send_push_to_user(
    session: Session,
    user: User,
    *,
    title: str,
    body: str,
    url: str = "/",
    tag: str = "",
) -> int:
    """Send push to all of user's subscriptions. Returns count of successful sends."""
    settings = get_settings()
    if not settings.has_vapid or not user.push_notifications:
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        log.warning("pywebpush not installed — push disabled")
        return 0

    subs = session.exec(
        select(PushSubscription).where(PushSubscription.user_id == user.id)
    ).all()
    if not subs:
        return 0

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": tag,
    }, ensure_ascii=False)

    vapid_claims = {"sub": settings.vapid_mailto or "mailto:noreply@health-mdt.local"}
    sent = 0
    stale_ids: list[int] = []

    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=vapid_claims,
                timeout=10,
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e, "response", None)
            status_code = getattr(status, "status_code", 0) if status else 0
            if status_code in (404, 410):
                stale_ids.append(sub.id)
                log.info("Removing stale push subscription %d (HTTP %d)", sub.id, status_code)
            else:
                log.warning("Push failed for sub %d: %s", sub.id, e)
        except Exception as e:
            log.warning("Push failed for sub %d: %s", sub.id, e)

    # Clean up stale subscriptions
    if stale_ids:
        for sid in stale_ids:
            sub_obj = session.get(PushSubscription, sid)
            if sub_obj:
                session.delete(sub_obj)
        session.commit()

    return sent
