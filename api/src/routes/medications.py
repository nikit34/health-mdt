"""Medication CRUD + dose reminder scheduling.

Design:
- Meds are short records (name/dose/frequency as free text) because real-world
  prescriptions are messy ("1/2 tab PRN"). Agents reason over the strings.
- `reminder_time` is a local HH:MM — scheduler picks active meds each morning
  and enqueues a Task per med if it's not already created today.
- `stopped_on` preserves history: a med stopped last month is still visible to
  agents (context: did blood pressure drop after stopping X?).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth_deps import get_current_user
from ..db import Medication, User
from ..db.session import get_session

router = APIRouter()


class MedicationIn(BaseModel):
    name: str
    dose: str = ""
    frequency: str = ""
    started_on: Optional[date] = None
    stopped_on: Optional[date] = None
    notes: str = ""
    reminder_time: Optional[str] = None  # "HH:MM"


@router.get("")
def list_meds(
    include_stopped: bool = False,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    stmt = select(Medication).where(Medication.user_id == user.id).order_by(Medication.started_on.desc())
    rows = session.exec(stmt).all()
    today = date.today()
    if not include_stopped:
        rows = [m for m in rows if not m.stopped_on or m.stopped_on >= today]
    return [_med_dict(m) for m in rows]


@router.post("")
def create_med(
    payload: MedicationIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    _validate_reminder_time(payload.reminder_time)
    m = Medication(
        user_id=user.id,
        name=payload.name.strip(),
        dose=payload.dose.strip(),
        frequency=payload.frequency.strip(),
        started_on=payload.started_on or date.today(),
        stopped_on=payload.stopped_on,
        notes=payload.notes,
        reminder_time=payload.reminder_time,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return _med_dict(m)


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    started_on: Optional[date] = None
    stopped_on: Optional[date] = None
    notes: Optional[str] = None
    reminder_time: Optional[str] = None


@router.put("/{med_id}")
def update_med(
    med_id: int,
    payload: MedicationUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    m = session.get(Medication, med_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    if "reminder_time" in data:
        _validate_reminder_time(data["reminder_time"])
    for k, v in data.items():
        setattr(m, k, v)
    session.add(m)
    session.commit()
    session.refresh(m)
    return _med_dict(m)


@router.delete("/{med_id}")
def delete_med(
    med_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    m = session.get(Medication, med_id)
    if not m or m.user_id != user.id:
        raise HTTPException(404)
    session.delete(m)
    session.commit()
    return {"ok": True}


def _med_dict(m: Medication) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "dose": m.dose,
        "frequency": m.frequency,
        "started_on": m.started_on.isoformat() if m.started_on else None,
        "stopped_on": m.stopped_on.isoformat() if m.stopped_on else None,
        "notes": m.notes,
        "reminder_time": m.reminder_time,
        "is_active": m.is_active,
    }


def _validate_reminder_time(rt: Optional[str]) -> None:
    if rt is None or rt == "":
        return
    parts = rt.split(":")
    if len(parts) != 2:
        raise HTTPException(400, "reminder_time must be HH:MM")
    try:
        h, mm = int(parts[0]), int(parts[1])
    except ValueError:
        raise HTTPException(400, "reminder_time must be HH:MM") from None
    if not (0 <= h < 24 and 0 <= mm < 60):
        raise HTTPException(400, "reminder_time out of range")
