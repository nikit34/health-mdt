"""Reports — briefs, MDT consilium on demand, history, PDF export."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session, select

from ..agents.orchestrator import generate_daily_brief, run_mdt_consilium
from ..auth_deps import get_current_user
from ..config import get_settings
from ..db import Brief, MdtReport, PubmedEvidence, User
from ..db.session import engine, get_session
from ..reports.pdf_export import render_mdt_pdf

router = APIRouter()


@router.post("/brief/generate")
def generate_brief_now(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "LLM credentials not configured — задай CLAUDE_CODE_OAUTH_TOKEN или ANTHROPIC_API_KEY")
    brief = generate_daily_brief(session, user)
    return _brief_dict(brief)


@router.get("/brief/latest")
def get_latest_brief(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict | None:
    b = session.exec(
        select(Brief).where(Brief.user_id == user.id).order_by(Brief.created_at.desc())
    ).first()
    return _brief_dict(b) if b else None


@router.get("/briefs")
def list_briefs(
    limit: int = Query(30, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
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
    user: User = Depends(get_current_user),
) -> dict:
    s = get_settings()
    if not s.has_llm:
        raise HTTPException(400, "LLM credentials not configured")
    bg.add_task(_run_mdt_bg, user.id, kind, window_days)
    return {"status": "started", "kind": kind, "window_days": window_days}


def _run_mdt_bg(user_id: int, kind: str, window_days: int) -> None:
    with Session(engine) as s:
        u = s.get(User, user_id)
        if u:
            run_mdt_consilium(s, u, kind=kind, window_days=window_days)


@router.get("/mdt/latest")
def get_latest_mdt(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict | None:
    r = session.exec(
        select(MdtReport).where(MdtReport.user_id == user.id).order_by(MdtReport.created_at.desc())
    ).first()
    return _mdt_dict(session, r) if r else None


@router.get("/mdt")
def list_mdt(
    limit: int = Query(10, le=50),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.exec(
        select(MdtReport)
        .where(MdtReport.user_id == user.id)
        .order_by(MdtReport.created_at.desc())
        .limit(limit)
    ).all()
    return [_mdt_dict(session, r) for r in rows]


@router.get("/mdt/{report_id}")
def get_mdt(
    report_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    r = session.get(MdtReport, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404)
    return _mdt_dict(session, r)


@router.get("/mdt/{report_id}/pdf")
def get_mdt_pdf(
    report_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Render MDT report as PDF — print-friendly, hand-to-physician format."""
    r = session.get(MdtReport, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404)
    pdf_bytes = render_mdt_pdf(session, r)
    filename = f"mdt-report-{r.created_at.date().isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    evidence: list[dict] = []
    if r.evidence_pmids:
        rows = session.exec(
            select(PubmedEvidence).where(PubmedEvidence.pmid.in_(r.evidence_pmids))
        ).all()
        seen: set[str] = set()
        for ev in rows:
            if ev.pmid in seen or not ev.pmid or ev.title == "(no results)":
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
