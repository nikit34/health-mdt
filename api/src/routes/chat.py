"""Ad-hoc chat with the GP agent — for the web chat widget and bot /ask."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session
from sse_starlette.sse import EventSourceResponse

from ..agents.context import build_context
from ..agents.registry import GP_AGENT
from ..auth_deps import get_current_user, validate_session_token_raw
from ..config import get_settings
from ..db import User
from ..db.session import engine, get_session

log = logging.getLogger(__name__)
router = APIRouter()


class AskIn(BaseModel):
    question: str
    window_days: int = 14


@router.post("/ask")
def ask(
    payload: AskIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured")

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


STREAM_SYSTEM_PROMPT = """Ты — семейный врач (GP), отвечающий пациенту.

Тебе дают JSON с его актуальным контекстом: метрики, анализы (с флагом valid=True/False),
чек-ины, активные проблемы. Отвечай как семейный врач, которого пациент знает 10 лет:
• конкретно, на основе данных; если данных не хватает — скажи прямо;
• 2-4 абзаца, без markdown-заголовков, без списков-пуль (простой текст, как живая речь);
• если видишь триггер — укажи его в финальном предложении в формате "⚠ <триггер>";
• не ставь диагнозов, не назначай лекарств.
"""


@router.get("/ask/stream")
async def ask_stream(
    question: str = Query(...),
    window_days: int = Query(14, ge=1, le=90),
    session_token: str = Query("", alias="session"),
):
    """SSE streaming GP response.

    Accepts session via query param because EventSource can't set headers.
    """
    settings = get_settings()
    if not settings.has_llm:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured")
    uid = validate_session_token_raw(session_token)
    if uid is None:
        raise HTTPException(401, "session_required")

    with Session(engine) as db:
        user = db.get(User, uid) if uid and uid > 1 else None
        if not user:
            # Fallback for single-user PIN mode where uid is placeholder 1
            from sqlmodel import select as _select
            user = db.exec(_select(User)).first()
        if not user:
            raise HTTPException(400, "user not initialized")
        ctx = build_context(db, user, window_days=window_days)

    prompt = (
        f"Вопрос пациента: «{question}»\n\n"
        f"Контекст пациента (JSON):\n{json.dumps(ctx.to_dict(), ensure_ascii=False, default=str, indent=2)}"
    )

    async def generator():
        try:
            yield {"event": "start", "data": ""}
            import asyncio
            loop = asyncio.get_event_loop()
            stream_iter = iter(GP_AGENT.stream(prompt, system_override=STREAM_SYSTEM_PROMPT))
            while True:
                chunk = await loop.run_in_executor(None, _safe_next, stream_iter)
                if chunk is _SENTINEL:
                    break
                yield {"event": "chunk", "data": chunk}
            yield {"event": "done", "data": ""}
        except Exception as e:
            log.exception("Streaming failed: %s", e)
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(generator())


_SENTINEL = object()


def _safe_next(it):
    try:
        return next(it)
    except StopIteration:
        return _SENTINEL
