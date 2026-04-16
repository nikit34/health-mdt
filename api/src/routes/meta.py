"""Meta/system endpoints — status, capabilities."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..auth_deps import optional_user
from ..config import get_settings
from ..db import Checkin, Document, LabResult, Metric, Task, User
from ..db.session import get_session

router = APIRouter(tags=["meta"])


@router.get("/status")
def status(
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> dict:
    """Return system readiness. Works without auth (used by login page).

    If user is authenticated, scope counts to that user.
    """
    s = get_settings()
    user_onboarded = False
    counts = {"metrics": 0, "labs": 0, "documents": 0, "open_tasks": 0, "checkins": 0}

    if user:
        user_onboarded = bool(user.birthdate or user.context)
        counts["metrics"] = len(session.exec(select(Metric.id).where(Metric.user_id == user.id)).all())
        counts["labs"] = len(session.exec(select(LabResult.id).where(LabResult.user_id == user.id)).all())
        counts["documents"] = len(session.exec(select(Document.id).where(Document.user_id == user.id)).all())
        counts["open_tasks"] = len(
            session.exec(select(Task.id).where(Task.user_id == user.id, Task.status == "open")).all()
        )
        counts["checkins"] = len(session.exec(select(Checkin.id).where(Checkin.user_id == user.id)).all())

    return {
        "version": "0.2.0",
        "auth_mode": "oauth" if s.has_oauth else "pin",
        "capabilities": {
            "llm": s.has_llm,
            "oura": s.has_oura,
            "telegram": s.has_telegram,
            "oauth": s.has_oauth,
            "smtp": s.has_smtp,
            "push": s.has_vapid,
        },
        "llm_auth_mode": s.llm_auth_mode,  # 'setup_token' | 'api_key' | 'none'
        "user_onboarded": user_onboarded,
        "authenticated": user is not None,
        "user": {
            "email": user.email,
            "name": user.name,
            "avatar_url": user.avatar_url,
        } if user else None,
        "counts": counts,
        "domain": s.domain,
    }
