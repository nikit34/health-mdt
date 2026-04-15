"""Shared auth helpers used across all routes.

In PIN mode:
  - Session token maps to "the" user (single-user mode). If no user exists, create one.
In OAuth mode:
  - Session token is a signed token that embeds user_id.
  - Only users returned from the OAuth callback can obtain a session.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlmodel import Session, select

from .config import get_settings
from .db import User
from .db.session import get_session

# In-memory PIN sessions (fine for single-user MVP)
_pin_sessions: dict[str, datetime] = {}
_PIN_SESSION_TTL = timedelta(days=30)

# OAuth session lifetime (signed token)
_OAUTH_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


def pin_session_store() -> dict[str, datetime]:
    """Expose the PIN session store so auth routes can mutate it."""
    return _pin_sessions


def _oauth_serializer() -> URLSafeTimedSerializer:
    s = get_settings()
    return URLSafeTimedSerializer(s.session_secret or "dev-only-not-for-prod", salt="health-mdt-session")


def issue_oauth_session(user_id: int) -> str:
    return _oauth_serializer().dumps({"uid": user_id})


def issue_pin_session() -> str:
    import secrets
    token = secrets.token_urlsafe(32)
    _pin_sessions[token] = datetime.utcnow() + _PIN_SESSION_TTL
    return token


def _resolve_user_from_token(token: str, session: Session) -> Optional[User]:
    settings = get_settings()
    if settings.has_oauth:
        try:
            data = _oauth_serializer().loads(token, max_age=_OAUTH_SESSION_MAX_AGE_SECONDS)
        except (BadSignature, SignatureExpired):
            return None
        uid = data.get("uid") if isinstance(data, dict) else None
        if not uid:
            return None
        return session.get(User, uid)
    # PIN mode
    if not settings.access_pin.strip():
        # Open mode — return or create single user
        return _single_user(session)
    if not token or token not in _pin_sessions:
        return None
    if _pin_sessions[token] < datetime.utcnow():
        _pin_sessions.pop(token, None)
        return None
    return _single_user(session)


def _single_user(session: Session) -> User:
    user = session.exec(select(User)).first()
    if not user:
        user = User()
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def get_current_user(
    x_session: str = Header(default="", alias="X-Session"),
    session: Session = Depends(get_session),
) -> User:
    """FastAPI dependency — resolves the current user or raises 401."""
    user = _resolve_user_from_token(x_session, session)
    if not user:
        raise HTTPException(status_code=401, detail="session_required")
    return user


def optional_user(
    x_session: str = Header(default="", alias="X-Session"),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401."""
    return _resolve_user_from_token(x_session, session)


def validate_session_token_raw(token: str) -> Optional[int]:
    """Pure-function variant for contexts without DI (SSE query params).

    Returns user_id on success, None on failure. Caller does its own 401 handling.
    """
    settings = get_settings()
    if settings.has_oauth:
        try:
            data = _oauth_serializer().loads(token, max_age=_OAUTH_SESSION_MAX_AGE_SECONDS)
            return data.get("uid") if isinstance(data, dict) else None
        except Exception:
            return None
    if not settings.access_pin.strip():
        return 1  # "any user" in open mode
    if token in _pin_sessions and _pin_sessions[token] >= datetime.utcnow():
        return 1
    return None
