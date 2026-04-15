"""Document upload & extraction."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from ..config import get_settings
from ..db import Document, User
from ..db.session import engine, get_session
from ..integrations.documents import process_medical_document
from .auth import require_session

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/upload")
async def upload_document(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(400, "user not initialized — complete onboarding first")

    settings = get_settings()
    dest_dir = settings.uploads_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Uniq filename
    suffix = Path(file.filename or "upload").suffix or ".bin"
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    dest = dest_dir / safe_name
    with dest.open("wb") as f:
        while chunk := await file.read(1 << 16):
            f.write(chunk)

    # Process in background so request returns fast
    bg.add_task(_process_in_background, user.id, dest, file.filename or safe_name, file.content_type or "application/octet-stream")
    return {"status": "accepted", "filename": file.filename}


def _process_in_background(user_id: int, path: Path, original: str, mime: str) -> None:
    with Session(engine) as s:
        u = s.get(User, user_id)
        if u:
            process_medical_document(s, u, path, original, mime)


@router.get("")
def list_documents(session: Session = Depends(get_session)) -> list[dict]:
    user = session.exec(select(User)).first()
    if not user:
        return []
    rows = session.exec(
        select(Document).where(Document.user_id == user.id).order_by(Document.uploaded_at.desc())
    ).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "uploaded_at": d.uploaded_at.isoformat(),
            "status": d.status,
            "summary": d.summary,
            "doc_type": (d.extracted or {}).get("doc_type"),
            "date": (d.extracted or {}).get("date"),
        }
        for d in rows
    ]


@router.get("/{doc_id}")
def get_document(doc_id: int, session: Session = Depends(get_session)) -> dict:
    d = session.get(Document, doc_id)
    if not d:
        raise HTTPException(404)
    return d.model_dump()
