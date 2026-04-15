"""PIN-based auth — simple for single-user MVP.

The PIN is set in .env (ACCESS_PIN) on deploy. Client sends it via X-PIN header;
we return a session token that the client keeps in a cookie/localStorage.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException

from ..config import get_settings

router = APIRouter()

# In-memory session store — fine for single-user MVP
_sessions: dict[str, datetime] = {}
_SESSION_TTL = timedelta(days=30)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


@router.post("/login")
def login(payload: dict) -> dict:
    pin = str(payload.get("pin", "")).strip()
    settings = get_settings()
    expected = settings.access_pin.strip()
    if not expected:
        # No PIN configured — everyone has access (local dev mode)
        token = _new_token()
        _sessions[token] = datetime.utcnow() + _SESSION_TTL
        return {"token": token, "mode": "open"}
    if not _constant_time_equals(pin, expected):
        raise HTTPException(status_code=401, detail="invalid_pin")
    token = _new_token()
    _sessions[token] = datetime.utcnow() + _SESSION_TTL
    return {"token": token, "mode": "authenticated"}


@router.post("/logout")
def logout(token: str = Header(default="", alias="X-Session")) -> dict:
    _sessions.pop(token, None)
    return {"ok": True}


def require_session(
    x_session: str = Header(default="", alias="X-Session"),
) -> None:
    """FastAPI dependency — raises 401 if session invalid."""
    settings = get_settings()
    if not settings.access_pin.strip():
        return  # open mode
    if not x_session or x_session not in _sessions:
        raise HTTPException(status_code=401, detail="session_required")
    if _sessions[x_session] < datetime.utcnow():
        _sessions.pop(x_session, None)
        raise HTTPException(status_code=401, detail="session_expired")


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
