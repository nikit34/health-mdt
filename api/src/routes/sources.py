"""Manual triggers for data sources — Oura sync, Apple Health import."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from ..auth_deps import get_current_user
from ..config import get_settings
from ..db import User
from ..db.session import engine, get_session
from ..integrations.apple_health import import_apple_health_xml
from ..integrations.oura import fetch_oura_daily

router = APIRouter()


@router.post("/oura/sync")
def oura_sync(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_oura:
        raise HTTPException(400, "OURA_PERSONAL_ACCESS_TOKEN not configured")
    return fetch_oura_daily(session, user)


@router.post("/apple-health/import")
async def apple_health_import(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    dest = settings.uploads_dir / f"apple_health_{uuid.uuid4().hex}.zip"
    with dest.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    bg.add_task(_import_in_background, user.id, dest)
    return {"status": "accepted", "filename": file.filename}


def _import_in_background(user_id: int, path: Path) -> None:
    with Session(engine) as s:
        u = s.get(User, user_id)
        if u:
            try:
                import_apple_health_xml(s, u, path)
            finally:
                path.unlink(missing_ok=True)
