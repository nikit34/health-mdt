"""User profile, check-ins, metrics browsing."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import Checkin, Metric, User
from ..db.session import get_session
from .auth import require_session

router = APIRouter(dependencies=[Depends(require_session)])


class UserUpdate(BaseModel):
    name: Optional[str] = None
    birthdate: Optional[date] = None
    sex: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    timezone: Optional[str] = None
    context: Optional[str] = None


@router.get("/me")
def get_me(session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        user = User()
        session.add(user)
        session.commit()
        session.refresh(user)
    return user.model_dump()


@router.put("/me")
def update_me(payload: UserUpdate, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        user = User()
        session.add(user)
        session.commit()
        session.refresh(user)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user.model_dump()


class CheckinIn(BaseModel):
    text: str
    mood: Optional[int] = None
    energy: Optional[int] = None
    sleep_quality: Optional[int] = None
    tags: list[str] = []


@router.post("/checkin")
def create_checkin(
    payload: CheckinIn,
    session: Session = Depends(get_session),
) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(404, "user not initialized")
    c = Checkin(
        user_id=user.id,
        text=payload.text,
        mood=payload.mood,
        energy=payload.energy,
        sleep_quality=payload.sleep_quality,
        tags=payload.tags,
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    return c.model_dump()


@router.get("/checkins")
def list_checkins(
    limit: int = Query(50, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    user = session.exec(select(User)).first()
    if not user:
        return []
    rows = session.exec(
        select(Checkin).where(Checkin.user_id == user.id).order_by(Checkin.ts.desc()).limit(limit)
    ).all()
    return [r.model_dump() for r in rows]


@router.get("/metrics")
def list_metrics(
    kind: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        return {"series": {}}
    since = datetime.utcnow() - timedelta(days=days)
    stmt = select(Metric).where(Metric.user_id == user.id, Metric.ts >= since)
    if kind:
        stmt = stmt.where(Metric.kind == kind)
    rows = session.exec(stmt.order_by(Metric.ts)).all()

    series: dict[str, list[dict]] = {}
    for r in rows:
        series.setdefault(r.kind, []).append({
            "ts": r.ts.isoformat(),
            "value": r.value,
            "unit": r.unit,
            "source": r.source,
        })
    return {"series": series, "count": len(rows)}
