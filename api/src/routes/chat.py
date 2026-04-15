"""Ad-hoc chat with the GP agent — for the web chat widget and bot /ask."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..agents.context import build_context
from ..agents.registry import GP_AGENT
from ..config import get_settings
from ..db import User
from ..db.session import get_session
from .auth import require_session

log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_session)])


class AskIn(BaseModel):
    question: str
    window_days: int = 14


@router.post("/ask")
def ask(payload: AskIn, session: Session = Depends(get_session)) -> dict:
    """One-shot Q&A with GP agent, grounded in current context."""
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured")
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(400, "user not initialized")

    ctx = build_context(session, user, window_days=payload.window_days)

    q_payload = {
        **ctx.to_dict(),
        "instruction": (
            f"Пациент задал вопрос: «{payload.question}». "
            "Ответь как семейный врач: конкретно, на основе доступных данных, "
            "честно когда данных не хватает. 2-4 абзаца. "
            "Верни JSON: {\"answer\": \"...\", \"confidence\": 0.0-1.0, \"needs_human_review\": bool, "
            "\"follow_ups\": [\"возможные следующие действия пациента\"]}"
        ),
    }
    resp = GP_AGENT.run(q_payload)
    answer = resp.narrative or resp.soap.get("assessment", "")
    return {
        "answer": answer,
        "confidence": resp.confidence,
        "safety_flags": resp.safety_flags,
        "follow_ups": [r.get("title", "") for r in resp.recommendations if r.get("title")],
    }
