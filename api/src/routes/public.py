"""Public (unauthenticated) routes — landing demo + waitlist capture.

Serves the marketing surface: a pre-baked sample MDT report so a prospect can
see the product without signing up, and a waitlist endpoint so interest is
measurable before billing goes live.

Rate-limit: waitlist is IP-throttled (5 posts per 60s, in-memory) to stop
form-spam without requiring a captcha during the prototype phase.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import MdtReport, User, WaitlistSignup
from ..db.session import engine
from .reports import _mdt_dict

router = APIRouter()

_RATE_WINDOW_SECONDS = 60
_RATE_LIMIT = 5
_rate_hits: dict[str, list[float]] = defaultdict(list)

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class WaitlistIn(BaseModel):
    email: str
    note: str = ""
    tier: str = ""


@router.get("/demo-report")
def demo_report() -> dict[str, Any]:
    """Return the pre-seeded monthly MDT report.

    This is what a prospect sees after clicking "Посмотреть пример" on the
    landing page. If no monthly report is seeded yet (fresh install not yet
    booted), we fall back to the latest weekly or 503.
    """
    with Session(engine) as s:
        report = s.exec(
            select(MdtReport)
            .where(MdtReport.kind == "monthly")
            .order_by(MdtReport.created_at.desc())
        ).first()
        if not report:
            report = s.exec(
                select(MdtReport).order_by(MdtReport.created_at.desc())
            ).first()
        if not report:
            raise HTTPException(503, "demo_not_seeded")

        payload = _mdt_dict(s, report)
        user = s.get(User, report.user_id)
        payload["patient"] = {
            "age": _age(user.birthdate) if user and user.birthdate else None,
            "sex": user.sex if user else None,
            "context": user.context if user else "",
        }
        return payload


@router.post("/waitlist")
def join_waitlist(payload: WaitlistIn, request: Request) -> dict[str, str]:
    """Capture an email for the waitlist. IP-throttled."""
    email = (payload.email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "invalid_email")

    ip = request.client.host if request.client else "0.0.0.0"
    ip_hash = hashlib.sha256(ip.encode()).hexdigest()
    now = time.time()
    hits = _rate_hits[ip_hash]
    hits[:] = [t for t in hits if now - t < _RATE_WINDOW_SECONDS]
    if len(hits) >= _RATE_LIMIT:
        raise HTTPException(429, "slow_down")
    hits.append(now)

    tier = (payload.tier or "").strip() or None
    with Session(engine) as s:
        # Idempotent on (email, tier) — re-submissions don't create duplicates
        existing = s.exec(
            select(WaitlistSignup)
            .where(WaitlistSignup.email == email, WaitlistSignup.tier == tier)
        ).first()
        if existing:
            return {"status": "already_on_list"}
        row = WaitlistSignup(
            email=email,
            note=(payload.note or "")[:500],
            tier=tier,
            ip_hash=ip_hash,
            user_agent=request.headers.get("user-agent", "")[:200],
            referrer=request.headers.get("referer", "")[:200],
        )
        s.add(row)
        s.commit()
    return {"status": "ok"}


def _age(birthdate: date) -> int:
    today = date.today()
    return today.year - birthdate.year - (
        (today.month, today.day) < (birthdate.month, birthdate.day)
    )
