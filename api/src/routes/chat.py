"""Ad-hoc chat with the GP agent — streams + persists conversation history.

Design:
- Every ask belongs to a Conversation (created implicitly if client omits id).
- Server persists user message before streaming starts; assistant reply is flushed
  on `done` or on abort. Partial text is saved on cancel so the user sees where it cut.
- SSE generator listens for client disconnect (asyncio.CancelledError) — on disconnect
  we close the Anthropic stream (stops further tokens) and persist whatever we have.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from ..agents.context import build_context
from ..agents.registry import GP_AGENT
from ..auth_deps import get_current_user, validate_session_token_raw
from ..config import get_settings
from ..db import ChatMessage, Conversation, User
from ..db.session import engine, get_session

log = logging.getLogger(__name__)
router = APIRouter()


# --- One-shot non-streaming (kept for bot / fallback) ---

class AskIn(BaseModel):
    question: str
    window_days: int = 14
    conversation_id: int | None = None


@router.post("/ask")
def ask(
    payload: AskIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "LLM credentials not configured")

    conv = _get_or_create_conversation(session, user, payload.conversation_id, payload.question)
    _save_message(session, conv, "user", payload.question)

    ctx = build_context(session, user, window_days=payload.window_days)
    history = _load_history(session, conv, exclude_last_user=True)
    q_payload = {
        **ctx.to_dict(),
        "conversation_history": history,
        "instruction": (
            f"Пациент задал вопрос: «{payload.question}». "
            "Учитывай предыдущие сообщения диалога (conversation_history). "
            "Ответь как семейный врач: конкретно, на основе доступных данных, "
            "честно когда данных не хватает. 2-4 абзаца. "
            "Верни JSON: {\"answer\": \"...\", \"confidence\": 0.0-1.0, \"needs_human_review\": bool, "
            "\"follow_ups\": [\"возможные следующие действия пациента\"]}"
        ),
    }
    resp = GP_AGENT.run(q_payload)
    answer = resp.narrative or resp.soap.get("assessment", "")
    follow_ups = [r.get("title", "") for r in resp.recommendations if r.get("title")]
    _save_message(
        session, conv, "assistant", answer,
        meta={
            "confidence": resp.confidence,
            "safety_flags": resp.safety_flags,
            "follow_ups": follow_ups,
        },
    )
    return {
        "conversation_id": conv.id,
        "answer": answer,
        "confidence": resp.confidence,
        "safety_flags": resp.safety_flags,
        "follow_ups": follow_ups,
    }


# --- Conversations CRUD for the UI ---

@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.exec(
        select(Conversation)
        .where(Conversation.user_id == user.id, Conversation.active == True)  # noqa: E712
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    ).all()
    return [{"id": c.id, "title": c.title or "Без названия", "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/conversations/{conv_id}")
def get_conversation(
    conv_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    conv = session.get(Conversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404)
    msgs = session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conv_id).order_by(ChatMessage.created_at)
    ).all()
    return {
        "id": conv.id,
        "title": conv.title,
        "updated_at": conv.updated_at.isoformat(),
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "meta": m.meta, "created_at": m.created_at.isoformat()}
            for m in msgs
        ],
    }


@router.delete("/conversations/{conv_id}")
def archive_conversation(
    conv_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    conv = session.get(Conversation, conv_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(404)
    conv.active = False
    session.add(conv)
    session.commit()
    return {"ok": True}


# --- Streaming endpoint ---

STREAM_SYSTEM_PROMPT = """Ты — семейный врач (GP), отвечающий пациенту.

Тебе дают JSON с его актуальным контекстом (метрики, анализы, чек-ины, активные
проблемы) и историей диалога (conversation_history: user/assistant сообщения).
Отвечай как семейный врач, которого пациент знает 10 лет:
• учитывай историю диалога — не задавай вопросов, на которые уже получил ответы;
• конкретно, на основе данных; если данных не хватает — скажи прямо;
• 2-4 абзаца, без markdown-заголовков, без списков-пуль (простой текст, как живая речь);
• если видишь триггер — укажи его в финальном предложении в формате "⚠ <триггер>";
• не ставь диагнозов, не назначай лекарств.
"""


@router.get("/ask/stream")
async def ask_stream(
    request: Request,
    question: str = Query(...),
    window_days: int = Query(14, ge=1, le=90),
    conversation_id: int | None = Query(None),
    session_token: str = Query("", alias="session"),
):
    """SSE streaming GP response with persisted conversation history.

    Session via query param (EventSource can't set headers).
    If conversation_id is missing/unknown, a new one is created.
    """
    settings = get_settings()
    if not settings.has_llm:
        raise HTTPException(400, "LLM credentials not configured")
    uid = validate_session_token_raw(session_token)
    if uid is None:
        raise HTTPException(401, "session_required")

    # Build context + persist user turn synchronously BEFORE starting the stream
    with Session(engine) as db:
        user = _resolve_user(db, uid)
        if not user:
            raise HTTPException(400, "user not initialized")
        conv = _get_or_create_conversation(db, user, conversation_id, question)
        _save_message(db, conv, "user", question)
        ctx = build_context(db, user, window_days=window_days)
        history = _load_history(db, conv, exclude_last_user=True)
        conv_id = conv.id

    prompt = (
        f"Вопрос пациента: «{question}»\n\n"
        f"История диалога (последние сообщения):\n{json.dumps(history, ensure_ascii=False, indent=2)}\n\n"
        f"Контекст пациента (JSON):\n{json.dumps(ctx.to_dict(), ensure_ascii=False, default=str, indent=2)}"
    )

    collected: list[str] = []

    async def generator():
        stream_iter = None
        try:
            yield {"event": "start", "data": json.dumps({"conversation_id": conv_id})}
            loop = asyncio.get_event_loop()
            stream_iter = iter(GP_AGENT.stream(prompt, system_override=STREAM_SYSTEM_PROMPT))
            while True:
                # Bail out promptly if the client disconnected
                if await request.is_disconnected():
                    log.info("Client disconnected mid-stream, conversation=%s", conv_id)
                    break
                chunk = await loop.run_in_executor(None, _safe_next, stream_iter)
                if chunk is _SENTINEL:
                    break
                collected.append(chunk)
                yield {"event": "chunk", "data": chunk}
            yield {"event": "done", "data": ""}
        except asyncio.CancelledError:
            log.info("SSE generator cancelled, conversation=%s", conv_id)
            raise
        except Exception as e:
            log.exception("Streaming failed: %s", e)
            yield {"event": "error", "data": str(e)}
        finally:
            # Close the Anthropic stream (stops token generation on server side)
            try:
                if stream_iter is not None and hasattr(stream_iter, "close"):
                    stream_iter.close()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Persist whatever assistant text we collected, even if partial
            final_text = "".join(collected).strip()
            if final_text:
                warns = [m.group(1).strip() for m in _warn_pattern.finditer(final_text)]
                with Session(engine) as db:
                    conv = db.get(Conversation, conv_id)
                    if conv:
                        _save_message(
                            db, conv, "assistant", final_text,
                            meta={"safety_flags": warns, "partial": await request.is_disconnected()},
                        )

    return EventSourceResponse(generator())


# --- Helpers ---

_SENTINEL = object()
_warn_pattern = re.compile(r"⚠\s*([^\n]+)")


def _safe_next(it):
    try:
        return next(it)
    except StopIteration:
        return _SENTINEL


def _resolve_user(db: Session, uid: int) -> User | None:
    if uid > 0:
        return db.get(User, uid)
    # uid==0 → open-mode sentinel, resolve single user
    return db.exec(select(User)).first()


def _get_or_create_conversation(
    session: Session, user: User, conv_id: int | None, first_msg: str
) -> Conversation:
    if conv_id:
        conv = session.get(Conversation, conv_id)
        if conv and conv.user_id == user.id:
            return conv
    title = (first_msg or "").strip().split("\n")[0][:60]
    conv = Conversation(user_id=user.id, title=title)
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return conv


def _save_message(
    session: Session,
    conv: Conversation,
    role: str,
    content: str,
    *,
    meta: dict | None = None,
) -> ChatMessage:
    m = ChatMessage(conversation_id=conv.id, role=role, content=content, meta=meta or {})
    session.add(m)
    conv.updated_at = datetime.utcnow()
    session.add(conv)
    session.commit()
    session.refresh(m)
    return m


def _load_history(
    session: Session, conv: Conversation, *, exclude_last_user: bool = False, limit: int = 20
) -> list[dict]:
    """Return last `limit` messages of the conversation in chronological order.

    If `exclude_last_user=True`, drops the most recent message IF it's the current
    user turn we're about to answer (avoids duplicating it in the instruction).
    """
    rows = session.exec(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))
    if exclude_last_user and rows and rows[-1].role == "user":
        rows = rows[:-1]
    return [{"role": r.role, "content": r.content} for r in rows]
