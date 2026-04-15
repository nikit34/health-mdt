"""Task management — full lifecycle including Apple Reminders export."""
from __future__ import annotations

import urllib.parse
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import Task, User
from ..db.session import get_session
from .auth import require_session

router = APIRouter(dependencies=[Depends(require_session)])


class TaskIn(BaseModel):
    title: str
    detail: str = ""
    priority: str = "normal"
    due: Optional[date] = None


@router.get("")
def list_tasks(
    status: Optional[str] = "open",
    session: Session = Depends(get_session),
) -> list[dict]:
    user = session.exec(select(User)).first()
    if not user:
        return []
    stmt = select(Task).where(Task.user_id == user.id)
    if status:
        stmt = stmt.where(Task.status == status)
    rows = session.exec(stmt.order_by(Task.created_at.desc())).all()
    return [_task_dict(t) for t in rows]


@router.post("")
def create_task(payload: TaskIn, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(400, "user not initialized")
    t = Task(
        user_id=user.id,
        created_by="user",
        title=payload.title,
        detail=payload.detail,
        priority=payload.priority,
        due=payload.due,
    )
    t.reminders_url = _apple_reminders_url(t)
    session.add(t)
    session.commit()
    session.refresh(t)
    return _task_dict(t)


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    detail: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[date] = None


@router.put("/{task_id}")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: Session = Depends(get_session),
) -> dict:
    t = session.get(Task, task_id)
    if not t:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    if payload.status in ("done", "dismissed"):
        t.closed_at = datetime.utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return _task_dict(t)


@router.delete("/{task_id}")
def delete_task(task_id: int, session: Session = Depends(get_session)) -> dict:
    t = session.get(Task, task_id)
    if not t:
        raise HTTPException(404)
    session.delete(t)
    session.commit()
    return {"ok": True}


def _task_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "detail": t.detail,
        "priority": t.priority,
        "status": t.status,
        "due": t.due.isoformat() if t.due else None,
        "created_at": t.created_at.isoformat(),
        "created_by": t.created_by,
        "age_days": (datetime.utcnow() - t.created_at).days,
        "reminders_url": t.reminders_url or _apple_reminders_url(t),
        "source_report_id": t.source_report_id,
    }


def _apple_reminders_url(t: Task) -> str:
    """x-apple-reminderkit:// URL to add to Apple Reminders via a Shortcut on iOS.

    On iOS the user taps this link → a shortcut picks up title/notes and creates a reminder.
    See docs/apple-reminders.md for the one-time shortcut setup.
    """
    params = {
        "title": t.title,
        "notes": t.detail or "",
    }
    if t.due:
        params["due"] = t.due.isoformat()
    # Custom scheme consumed by the user's "Add to Reminders" shortcut
    return "shortcuts://run-shortcut?name=HealthMDT%20Add&input=" + urllib.parse.quote(
        f"{t.title}||{t.detail or ''}||{t.due.isoformat() if t.due else ''}"
    )
