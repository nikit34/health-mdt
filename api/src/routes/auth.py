"""Auth routes — PIN (single-user) and OAuth Google (multi-user).

AUTH_MODE decides which paths are active:
  - "pin"   (default): /auth/login → PIN check → session token
  - "oauth" (multi):   /auth/oauth/google → redirect to Google; /auth/callback → upsert user
"""
from __future__ import annotations

import hmac
import logging
import urllib.parse
from datetime import datetime

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from ..auth_deps import (
    issue_oauth_session,
    issue_pin_session,
    pin_session_store,
)
from ..config import get_settings
from ..db import User
from ..db.session import get_session

log = logging.getLogger(__name__)
router = APIRouter()

# --- OAuth client (Google) ---
_oauth_client: OAuth | None = None


def _get_oauth() -> OAuth:
    global _oauth_client
    if _oauth_client is None:
        s = get_settings()
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=s.oauth_google_client_id,
            client_secret=s.oauth_google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth_client = oauth
    return _oauth_client


# --- PIN mode ---

@router.post("/login")
def login(payload: dict) -> dict:
    settings = get_settings()
    if settings.has_oauth:
        raise HTTPException(400, "auth_mode=oauth — use /auth/oauth/google")
    pin = str(payload.get("pin", "")).strip()
    expected = settings.access_pin.strip()
    if not expected:
        return {"token": issue_pin_session(), "mode": "open"}
    if not _constant_time_equals(pin, expected):
        raise HTTPException(status_code=401, detail="invalid_pin")
    return {"token": issue_pin_session(), "mode": "authenticated"}


@router.post("/logout")
def logout(token: str = Header(default="", alias="X-Session")) -> dict:
    pin_session_store().pop(token, None)
    return {"ok": True}


@router.get("/mode")
def auth_mode() -> dict:
    s = get_settings()
    return {
        "mode": "oauth" if s.has_oauth else "pin",
        "providers": ["google"] if s.has_oauth else [],
        "pin_required": bool(s.access_pin.strip()) if not s.has_oauth else False,
    }


# --- OAuth mode ---

@router.get("/oauth/google")
async def oauth_google_login(request: Request):
    settings = get_settings()
    if not settings.has_oauth:
        raise HTTPException(400, "OAuth not configured")
    redirect_uri = _redirect_uri(request)
    oauth = _get_oauth()
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/oauth/google/callback")
async def oauth_google_callback(
    request: Request,
    session: Session = Depends(get_session),
):
    settings = get_settings()
    if not settings.has_oauth:
        raise HTTPException(400, "OAuth not configured")
    oauth = _get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        log.warning("OAuth error: %s", e)
        raise HTTPException(400, f"oauth_error: {e}")

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    sub = userinfo.get("sub") or ""
    name = userinfo.get("name") or email.split("@")[0] if email else "User"
    avatar = userinfo.get("picture")

    if not email or not sub:
        raise HTTPException(400, "oauth_no_email")

    # Allowlist check
    allowed = settings.allowed_email_list
    if allowed and email not in allowed:
        return HTMLResponse(
            f"<h1>Доступ ограничен</h1><p>Email {email} не в списке разрешённых на этом инстансе.</p>",
            status_code=403,
        )

    # Upsert user
    user = session.exec(select(User).where(User.email == email)).first()
    if not user:
        user = User(
            email=email,
            name=name,
            oauth_provider="google",
            oauth_sub=sub,
            avatar_url=avatar,
        )
        session.add(user)
    else:
        user.oauth_provider = "google"
        user.oauth_sub = sub
        user.avatar_url = avatar or user.avatar_url
        if not user.name:
            user.name = name
    session.commit()
    session.refresh(user)

    # Issue signed session and return to frontend
    token_str = issue_oauth_session(user.id)
    # Frontend root page will pick `?session=` from URL and store in localStorage
    return RedirectResponse(url=f"/?session={urllib.parse.quote(token_str)}")


def _redirect_uri(request: Request) -> str:
    settings = get_settings()
    if settings.domain and settings.domain != "localhost":
        return f"https://{settings.domain}/api/auth/oauth/google/callback"
    # Dev: http
    host = request.headers.get("host", "localhost:8000")
    proto = "https" if request.url.scheme == "https" else "http"
    return f"{proto}://{host}/api/auth/oauth/google/callback"


# --- Back-compat helpers used by existing code ---

def require_session(
    x_session: str = Header(default="", alias="X-Session"),
) -> None:
    """Back-compat: some routes still use this dep (pre-OAuth).

    For PIN mode it validates against the PIN session store; for OAuth it accepts
    any signed token. New code should use `get_current_user` from auth_deps.
    """
    validate_session_token(x_session)


def validate_session_token(token: str) -> None:
    from ..auth_deps import validate_session_token_raw
    uid = validate_session_token_raw(token)
    if uid is None:
        raise HTTPException(status_code=401, detail="session_required")


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
