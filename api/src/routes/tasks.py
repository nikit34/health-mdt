"""Task management — full lifecycle including Apple Reminders export."""
from __future__ import annotations

import urllib.parse
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth_deps import get_current_user
from ..db import Task, User
from ..db.session import get_session

router = APIRouter()


class TaskIn(BaseModel):
    title: str
    detail: str = ""
    priority: str = "normal"
    due: Optional[date] = None


@router.get("")
def list_tasks(
    status: Optional[str] = "open",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    stmt = select(Task).where(Task.user_id == user.id)
    if status:
        stmt = stmt.where(Task.status == status)
    rows = session.exec(stmt.order_by(Task.created_at.desc())).all()
    return [_task_dict(t) for t in rows]


@router.post("")
def create_task(
    payload: TaskIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
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
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    t = session.get(Task, task_id)
    if not t or t.user_id != user.id:
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
def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    t = session.get(Task, task_id)
    if not t or t.user_id != user.id:
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
    return "shortcuts://run-shortcut?name=HealthMDT%20Add&input=" + urllib.parse.quote(
        f"{t.title}||{t.detail or ''}||{t.due.isoformat() if t.due else ''}"
    )
