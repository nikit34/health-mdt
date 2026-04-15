"""Orchestration — run MDT consilium, daily brief, synthesis.

Flow (weekly MDT):
  1. Build context bundle (7d window).
  2. Each lifestyle agent produces a short note (parallel).
  3. Each MDT specialist produces a SOAP note (parallel), given context + lifestyle notes.
  4. PubMed fetches evidence for unique queries surfaced by specialists.
  5. GP synthesizes: problem list + plan + safety net.

Flow (daily brief):
  1. Build 1-day context.
  2. Lifestyle agents only (fast).
  3. GP writes 4-7 sentence morning brief.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
from dataclasses import asdict
from datetime import date, datetime

from sqlmodel import Session, select

from ..db import Brief, MdtReport, PubmedEvidence, Task, User
from ..integrations.pubmed import fetch_pubmed_evidence
from ..integrations.semantic_scholar import fetch_scholar_evidence
from .base import Agent, AgentResponse
from .context import build_context
from .registry import GP_AGENT, LIFESTYLE_AGENTS, MDT_SPECIALISTS

log = logging.getLogger(__name__)


def _run_parallel(agents: list[Agent], payload: dict, max_workers: int = 9) -> list[AgentResponse]:
    """Run agents concurrently. LLM calls are I/O-bound so threads are fine."""
    results: list[AgentResponse] = []
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(a.run, payload): a for a in agents}
        for fut in cf.as_completed(futures):
            agent = futures[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                log.exception("Agent %s failed: %s", agent.name, e)
                results.append(AgentResponse(
                    agent_name=agent.name,
                    role=agent.role,
                    narrative=f"[агент упал: {e}]",
                    confidence=0.0,
                ))
    return results


def run_mdt_consilium(
    session: Session,
    user: User,
    *,
    window_days: int = 7,
    kind: str = "weekly",
    fetch_evidence: bool = True,
) -> MdtReport:
    """Full MDT consilium → persisted MdtReport + derived Tasks."""
    log.info("Starting MDT consilium (kind=%s, window=%dd)", kind, window_days)
    ctx = build_context(session, user, window_days=window_days)
    ctx_dict = ctx.to_dict()

    # Step 1: lifestyle agents — they get raw context
    lifestyle_notes = _run_parallel(LIFESTYLE_AGENTS, ctx_dict)
    ctx_dict["lifestyle_notes"] = [
        {"agent": r.agent_name, "role": r.role, "narrative": r.narrative, "flags": r.safety_flags}
        for r in lifestyle_notes
    ]

    # Step 2: specialists — get context + lifestyle notes
    specialist_notes = _run_parallel(MDT_SPECIALISTS, ctx_dict)

    # Step 3: Evidence grounding — PubMed + Semantic Scholar in parallel
    all_queries: set[str] = set()
    for r in specialist_notes:
        all_queries.update(r.evidence_queries[:2])  # cap per agent
    queries_list = list(all_queries)[:8]
    pmids: list[str] = []
    scholar_records: list[dict] = []
    if fetch_evidence and queries_list:
        pubmed_map: dict[str, list[str]] = {}
        scholar_map: dict[str, list[dict]] = {}
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            fut_pm = pool.submit(fetch_pubmed_evidence, queries_list, session=session)
            fut_ss = pool.submit(fetch_scholar_evidence, queries_list, session=session)
            try:
                pubmed_map = fut_pm.result(timeout=30)
            except Exception as e:
                log.warning("PubMed fetch failed: %s", e)
            try:
                scholar_map = fut_ss.result(timeout=30)
            except Exception as e:
                log.warning("Semantic Scholar fetch failed: %s", e)

        for pmid_list in pubmed_map.values():
            pmids.extend(pmid_list)
        for records in scholar_map.values():
            scholar_records.extend(records)
        # Attach pmids back to specialists whose queries hit
        for r in specialist_notes:
            for q in r.evidence_queries:
                r.evidence_pmids.extend(pubmed_map.get(q, []))

    # Step 4: GP synthesis — collate everything
    gp_payload = {
        **ctx_dict,
        "specialist_notes": [
            {
                "agent": r.agent_name,
                "role": r.role,
                "soap": r.soap,
                "narrative": r.narrative,
                "recommendations": r.recommendations,
                "safety_flags": r.safety_flags,
                "evidence_pmids": r.evidence_pmids,
                "confidence": r.confidence,
            }
            for r in specialist_notes
        ],
        "scholar_evidence": [
            {"title": s["title"], "venue": s.get("journal"), "year": s.get("year"), "citations": s.get("citations", 0)}
            for s in scholar_records[:10]
        ],
        "instruction": (
            f"Составь {kind} GP-отчёт. Верни JSON по схеме из system-промпта "
            "(gp_synthesis, problem_list, plan, safety_net, evidence_pmids). "
            "Не менее 2 safety-net триггеров. plan.action — максимум 5 задач, максимально конкретные."
        ),
    }
    gp_response = GP_AGENT.run(gp_payload)
    gp_raw = gp_response.raw
    # GP returns richer structure — parse from narrative-style JSON
    gp_parsed = _parse_gp_output(gp_response)

    # Step 5: persist
    # Merge evidence: PubMed PMIDs + Scholar records (stored as PMID when available, or SS-URL)
    scholar_refs = [s for s in scholar_records if s.get("title")]
    all_evidence_keys = list(dict.fromkeys(
        pmids + gp_parsed.get("evidence_pmids", []) + [s["pmid"] for s in scholar_refs if s.get("pmid")]
    ))
    report = MdtReport(
        user_id=user.id,
        kind=kind,
        specialist_notes={
            r.agent_name: {
                "role": r.role,
                "soap": r.soap,
                "narrative": r.narrative,
                "recommendations": r.recommendations,
                "safety_flags": r.safety_flags,
                "evidence_pmids": r.evidence_pmids,
                "confidence": r.confidence,
            }
            for r in lifestyle_notes + specialist_notes
        },
        gp_synthesis=gp_parsed.get("gp_synthesis", gp_response.narrative or ""),
        problem_list=gp_parsed.get("problem_list", []),
        safety_net=gp_parsed.get("safety_net", []),
        evidence_pmids=all_evidence_keys,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    # Create tasks from GP plan.action
    plan_action = gp_parsed.get("plan", {}).get("action", [])
    for item in plan_action[:5]:
        due = _parse_due(item.get("due_days"))
        t = Task(
            user_id=user.id,
            created_by="gp",
            title=item.get("title", "")[:200],
            detail=item.get("detail", ""),
            priority=item.get("priority", "normal"),
            due=due,
            source_report_id=report.id,
        )
        session.add(t)
    session.commit()

    log.info("MDT report %d done. tokens=%s", report.id, gp_raw.get("usage"))
    return report


def generate_daily_brief(
    session: Session,
    user: User,
    *,
    for_date: date | None = None,
) -> Brief:
    """Short morning brief from GP using lifestyle agent notes only."""
    for_date = for_date or date.today()
    ctx = build_context(session, user, window_days=2)
    ctx_dict = ctx.to_dict()

    # Recent MDT report context (last weekly) for continuity
    latest_report = session.exec(
        select(MdtReport)
        .where(MdtReport.user_id == user.id)
        .order_by(MdtReport.created_at.desc())
    ).first()
    if latest_report:
        ctx_dict["latest_gp_synthesis"] = latest_report.gp_synthesis
        ctx_dict["active_problems"] = [
            p for p in latest_report.problem_list if p.get("status") == "active"
        ]

    # Lifestyle briefs (fast, cheap)
    notes = _run_parallel(LIFESTYLE_AGENTS, ctx_dict)
    ctx_dict["lifestyle_notes"] = [
        {"agent": r.agent_name, "narrative": r.narrative, "flags": r.safety_flags}
        for r in notes
    ]

    brief_payload = {
        **ctx_dict,
        "instruction": (
            f"Напиши утренний бриф на {for_date.isoformat()}. 4–7 предложений. "
            "Начни с одного предложения про вчера (контекст), потом 2–4 предложения про "
            "что это значит именно для этого человека (с учётом контекста пациента и активных проблем), "
            "заверши одной конкретной рекомендацией на сегодня. Никаких цифр ради цифр. "
            "Верни JSON: {\"brief\": \"...\", \"highlights\": [\"3–5 ключевых тезисов\"]}"
        ),
    }
    resp = GP_AGENT.run(brief_payload)
    parsed = _parse_brief_output(resp)

    b = Brief(
        user_id=user.id,
        for_date=for_date,
        text=parsed.get("brief", resp.narrative or ""),
        lifestyle_flags={r.agent_name: r.safety_flags for r in notes if r.safety_flags},
        highlights=parsed.get("highlights", []),
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


# --- helpers ---

def _parse_gp_output(resp: AgentResponse) -> dict:
    """GP agent returns a custom schema — read from the full parsed payload."""
    p = resp.payload or {}
    out = {
        "gp_synthesis": p.get("gp_synthesis") or resp.narrative or resp.soap.get("assessment", ""),
        "problem_list": p.get("problem_list") or [],
        "plan": p.get("plan") or {"action": [], "monitor": [], "review": []},
        "safety_net": p.get("safety_net") or resp.safety_flags or [],
        "evidence_pmids": p.get("evidence_pmids") or resp.evidence_pmids,
    }
    # Ensure plan shape
    plan = out["plan"]
    for k in ("action", "monitor", "review"):
        plan.setdefault(k, [])
    # Fallback: if the GP dumped a brief-shaped output with recommendations, promote them
    if not plan["action"] and resp.recommendations:
        plan["action"] = [
            {
                "title": r.get("title", ""),
                "detail": r.get("detail", ""),
                "priority": r.get("priority", "normal"),
                "due_days": r.get("due_days", 0),
            }
            for r in resp.recommendations
        ]
    return out


def _parse_brief_output(resp: AgentResponse) -> dict:
    """Brief-specific output parsing: GP returned `brief` + `highlights`."""
    p = resp.payload or {}
    return {
        "brief": p.get("brief") or resp.narrative or resp.soap.get("assessment", ""),
        "highlights": p.get("highlights") or [r.get("title", "") for r in resp.recommendations if r.get("title")],
    }


def _parse_due(due_days: int | str | None) -> date | None:
    if due_days is None:
        return None
    try:
        days = int(due_days)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    from datetime import timedelta
    return date.today() + timedelta(days=days)
