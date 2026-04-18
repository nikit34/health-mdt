"""Manual triggers for data sources — Apple Health XML import.

Withings lives in its own router at /sources/withings (OAuth-heavy).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlmodel import Session

from ..auth_deps import get_current_user
from ..config import get_settings
from ..db import User
from ..db.session import engine
from ..integrations.apple_health import import_apple_health_xml

router = APIRouter()


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
