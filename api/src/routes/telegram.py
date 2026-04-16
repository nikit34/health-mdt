"""Telegram pairing — generates temporary codes for multi-user bot linking.

Flow:
1. User clicks "Привязать Telegram" in web Settings.
2. Server generates a 6-char pairing code → POST /telegram/pair-code.
3. User sends `/pair <code>` to the bot.
4. Bot calls verify_pairing_code() → links chat_id to user.
5. Web UI shows "Привязан" with unpair button.
"""
from __future__ import annotations

import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..auth_deps import get_current_user
from ..config import get_settings
from ..db import User
from ..db.session import get_session

router = APIRouter()

# In-memory pairing store: {code: (user_id, expires_ts)}
_pairing_codes: dict[str, tuple[int, float]] = {}
_CODE_TTL_SECONDS = 300  # 5 minutes


def _generate_code() -> str:
    """Generate a 6-char alphanumeric code, avoiding ambiguous characters."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _cleanup_expired() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _pairing_codes.items() if exp < now]
    for k in expired:
        _pairing_codes.pop(k, None)


@router.post("/pair-code")
def generate_pair_code(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Generate a temporary pairing code for linking this user to a Telegram chat."""
    if not get_settings().has_telegram:
        raise HTTPException(400, "Telegram bot not configured (TELEGRAM_BOT_TOKEN missing)")

    _cleanup_expired()

    # Invalidate any existing codes for this user
    to_remove = [k for k, (uid, _) in _pairing_codes.items() if uid == user.id]
    for k in to_remove:
        _pairing_codes.pop(k, None)

    code = _generate_code()
    _pairing_codes[code] = (user.id, time.time() + _CODE_TTL_SECONDS)
    return {"code": code, "ttl_seconds": _CODE_TTL_SECONDS}


@router.delete("/unpair")
def unpair(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Remove Telegram chat linking for the current user."""
    user.telegram_chat_id = None
    session.add(user)
    session.commit()
    return {"ok": True}


@router.get("/status")
def telegram_status(
    user: User = Depends(get_current_user),
) -> dict:
    return {
        "paired": user.telegram_chat_id is not None,
        "chat_id": user.telegram_chat_id,
        "bot_configured": get_settings().has_telegram,
    }


def verify_pairing_code(code: str, chat_id: int) -> int | None:
    """Called by the bot to verify a pairing code and link the chat.

    Returns user_id on success, None on failure.
    """
    _cleanup_expired()
    code = code.strip().upper()
    entry = _pairing_codes.pop(code, None)
    if not entry:
        return None
    user_id, expires = entry
    if time.time() > expires:
        return None
    return user_id
