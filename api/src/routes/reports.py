"""Reports — briefs, MDT consilium on demand, history."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..agents.orchestrator import generate_daily_brief, run_mdt_consilium
from ..config import get_settings
from ..db import Brief, MdtReport, PubmedEvidence, User
from ..db.session import engine, get_session
from .auth import require_session

router = APIRouter(dependencies=[Depends(require_session)])


@router.post("/brief/generate")
def generate_brief_now(session: Session = Depends(get_session)) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured — агенты выключены")
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(400, "user not initialized")
    brief = generate_daily_brief(session, user)
    return _brief_dict(brief)


@router.get("/brief/latest")
def get_latest_brief(session: Session = Depends(get_session)) -> dict | None:
    user = session.exec(select(User)).first()
    if not user:
        return None
    b = session.exec(
        select(Brief).where(Brief.user_id == user.id).order_by(Brief.created_at.desc())
    ).first()
    return _brief_dict(b) if b else None


@router.get("/briefs")
def list_briefs(
    limit: int = Query(30, le=100),
    session: Session = Depends(get_session),
) -> list[dict]:
    user = session.exec(select(User)).first()
    if not user:
        return []
    rows = session.exec(
        select(Brief)
        .where(Brief.user_id == user.id)
        .order_by(Brief.created_at.desc())
        .limit(limit)
    ).all()
    return [_brief_dict(b) for b in rows]


@router.post("/mdt/run")
def run_mdt_now(
    bg: BackgroundTasks,
    kind: str = "weekly",
    window_days: int = 7,
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured")
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(400, "user not initialized")
    # Run in background — can take 30-60s
    bg.add_task(_run_mdt_bg, user.id, kind, window_days)
    return {"status": "started", "kind": kind, "window_days": window_days}


def _run_mdt_bg(user_id: int, kind: str, window_days: int) -> None:
    with Session(engine) as s:
        u = s.get(User, user_id)
        if u:
            run_mdt_consilium(s, u, kind=kind, window_days=window_days)


@router.get("/mdt/latest")
def get_latest_mdt(session: Session = Depends(get_session)) -> dict | None:
    user = session.exec(select(User)).first()
    if not user:
        return None
    r = session.exec(
        select(MdtReport).where(MdtReport.user_id == user.id).order_by(MdtReport.created_at.desc())
    ).first()
    return _mdt_dict(session, r) if r else None


@router.get("/mdt")
def list_mdt(
    limit: int = Query(10, le=50),
    session: Session = Depends(get_session),
) -> list[dict]:
    user = session.exec(select(User)).first()
    if not user:
        return []
    rows = session.exec(
        select(MdtReport)
        .where(MdtReport.user_id == user.id)
        .order_by(MdtReport.created_at.desc())
        .limit(limit)
    ).all()
    return [_mdt_dict(session, r) for r in rows]


@router.get("/mdt/{report_id}")
def get_mdt(report_id: int, session: Session = Depends(get_session)) -> dict:
    r = session.get(MdtReport, report_id)
    if not r:
        raise HTTPException(404)
    return _mdt_dict(session, r)


def _brief_dict(b: Brief) -> dict:
    return {
        "id": b.id,
        "for_date": b.for_date.isoformat(),
        "created_at": b.created_at.isoformat(),
        "text": b.text,
        "highlights": b.highlights,
        "lifestyle_flags": b.lifestyle_flags,
    }


def _mdt_dict(session: Session, r: MdtReport) -> dict:
    # Fetch evidence details
    evidence: list[dict] = []
    if r.evidence_pmids:
        rows = session.exec(
            select(PubmedEvidence).where(PubmedEvidence.pmid.in_(r.evidence_pmids))
        ).all()
        seen: set[str] = set()
        for ev in rows:
            if ev.pmid in seen or not ev.pmid:
                continue
            seen.add(ev.pmid)
            evidence.append({
                "pmid": ev.pmid,
                "title": ev.title,
                "journal": ev.journal,
                "year": ev.pub_year,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{ev.pmid}/",
            })
    return {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "kind": r.kind,
        "specialist_notes": r.specialist_notes,
        "gp_synthesis": r.gp_synthesis,
        "problem_list": r.problem_list,
        "safety_net": r.safety_net,
        "evidence": evidence,
    }
