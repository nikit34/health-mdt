"""Withings OAuth flow + sync endpoints.

Flow:
  GET /sources/withings/connect           → returns authorize_url for the frontend to redirect to
  GET /sources/withings/callback?code=... → exchanges code, persists tokens, redirects to /settings
  GET /sources/withings/status            → is this user connected? when last synced?
  POST /sources/withings/sync             → pull latest measures now
  DELETE /sources/withings/disconnect     → clear tokens
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from ..auth_deps import get_current_user, validate_session_token_raw
from ..config import get_settings
from ..db import Metric, User
from ..db.session import engine, get_session
from ..integrations.withings import (
    build_authorize_url,
    disconnect as withings_disconnect,
    exchange_code_for_token,
    fetch_withings,
    persist_token,
)

log = logging.getLogger(__name__)
router = APIRouter()

# In-memory OAuth state store — short-lived (5 min), maps state → user_id.
# Prevents CSRF on the callback (state must match the user who initiated the connect).
_state_store: dict[str, tuple[int, float]] = {}
_STATE_TTL_SECONDS = 300


def _cleanup_states() -> None:
    now = time.time()
    for k in list(_state_store.keys()):
        if _state_store[k][1] < now:
            _state_store.pop(k, None)


def _redirect_uri(request: Request) -> str:
    s = get_settings()
    if s.domain and s.domain != "localhost":
        return f"https://{s.domain}/api/sources/withings/callback"
    host = request.headers.get("host", "localhost:8000")
    proto = "https" if request.url.scheme == "https" else "http"
    return f"{proto}://{host}/api/sources/withings/callback"


@router.get("/connect")
def connect(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Return the Withings consent URL. Frontend redirects the browser to it."""
    s = get_settings()
    if not s.has_withings:
        raise HTTPException(400, "withings_app_not_configured")

    _cleanup_states()
    state = secrets.token_urlsafe(24)
    _state_store[state] = (user.id, time.time() + _STATE_TTL_SECONDS)

    url = build_authorize_url(state=state, redirect_uri=_redirect_uri(request))
    return {"authorize_url": url}


@router.get("/callback")
def callback(
    request: Request,
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
    session: Session = Depends(get_session),
):
    """OAuth callback — exchange code, persist tokens, redirect back to UI."""
    _cleanup_states()

    if error:
        return RedirectResponse(url=f"/settings?withings_error={error}")
    if not code or not state:
        return RedirectResponse(url="/settings?withings_error=missing_code")

    entry = _state_store.pop(state, None)
    if not entry:
        return RedirectResponse(url="/settings?withings_error=invalid_state")
    user_id, expires = entry
    if time.time() > expires:
        return RedirectResponse(url="/settings?withings_error=state_expired")

    user = session.get(User, user_id)
    if not user:
        return RedirectResponse(url="/settings?withings_error=unknown_user")

    try:
        token_payload = exchange_code_for_token(code, _redirect_uri(request))
    except Exception as e:
        log.warning("Withings code exchange failed: %s", e)
        return RedirectResponse(url="/settings?withings_error=exchange_failed")

    persist_token(session, user, token_payload)

    # Kick off an initial background sync so the dashboard has data immediately.
    try:
        fetch_withings(session, user)
    except Exception as e:
        log.info("Withings initial sync will retry in scheduler: %s", e)

    return RedirectResponse(url="/settings?withings_connected=1#withings")


@router.post("/sync")
def sync(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_withings:
        raise HTTPException(400, "withings_app_not_configured")
    if not user.withings_access_token:
        raise HTTPException(400, "user_not_connected")
    return fetch_withings(session, user)


@router.delete("/disconnect")
def disconnect(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    withings_disconnect(session, user)
    return {"ok": True}


@router.get("/status")
def status(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    # Last Withings metric for this user — gives the UI a "last synced at"
    last = session.exec(
        select(Metric)
        .where(Metric.user_id == user.id, Metric.source == "withings")
        .order_by(Metric.ts.desc())
        .limit(1)
    ).first()
    return {
        "app_configured": s.has_withings,
        "connected": bool(user.withings_access_token),
        "expires_at": user.withings_expires_at.isoformat() if user.withings_expires_at else None,
        "last_sync_at": last.ts.isoformat() if last else None,
    }
