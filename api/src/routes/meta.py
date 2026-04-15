"""Meta/system endpoints — status, capabilities."""
from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import Session, select

from ..config import get_settings
from ..db import Checkin, Document, LabResult, Metric, Task, User
from ..db.session import engine

router = APIRouter(tags=["meta"])


@router.get("/status")
def status() -> dict:
    """Return system readiness — used by onboarding UI to know what's connected."""
    s = get_settings()
    with Session(engine) as session:
        user = session.exec(select(User)).first()
        user_onboarded = bool(user and (user.birthdate or user.context))
        n_metrics = session.exec(select(Metric.id)).all() if user else []
        n_labs = session.exec(select(LabResult.id)).all() if user else []
        n_docs = session.exec(select(Document.id)).all() if user else []
        n_tasks = session.exec(select(Task.id).where(Task.status == "open")).all() if user else []
        n_checkins = session.exec(select(Checkin.id)).all() if user else []

    return {
        "version": "0.1.0",
        "capabilities": {
            "llm": s.has_llm,
            "oura": s.has_oura,
            "telegram": s.has_telegram,
        },
        "user_onboarded": user_onboarded,
        "counts": {
            "metrics": len(n_metrics),
            "labs": len(n_labs),
            "documents": len(n_docs),
            "open_tasks": len(n_tasks),
            "checkins": len(n_checkins),
        },
        "domain": s.domain,
    }
