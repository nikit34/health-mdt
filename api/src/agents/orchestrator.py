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

    # Monthly review: include prior weekly reports as "recent consilia" so the
    # GP can retrospect on what was raised and whether it resolved.
    if kind == "monthly":
        ctx_dict["prior_reports"] = _prior_reports_for_retrospect(session, user, limit=5)

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
    pubmed_map: dict[str, list[str]] = {}
    scholar_map: dict[str, list[dict]] = {}
    if fetch_evidence and queries_list:
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

        # Attach PMIDs back to specialists whose queries hit
        for r in specialist_notes:
            for q in r.evidence_queries:
                r.evidence_pmids.extend(pubmed_map.get(q, []))

    # Dedup evidence: one record per PMID (PubMed wins — richer abstract),
    # fall back to Semantic Scholar paperId when no PMID. Gives GP a single
    # canonical list of references instead of overlapping noise.
    unified_evidence = _unify_evidence(pubmed_map, scholar_map, session)
    pmids = [e["pmid"] for e in unified_evidence if e.get("pmid")]
    scholar_records = [e for e in unified_evidence if not e.get("pmid") and e.get("ss_id")]

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
        "evidence": [
            {
                "ref": e["pmid"] or e.get("ss_id", ""),
                "title": e["title"],
                "venue": e.get("journal", ""),
                "year": e.get("year"),
                "source": e.get("source", ""),
                "url": e.get("url", ""),
            }
            for e in unified_evidence[:12]
        ],
        "instruction": (
            f"Составь {kind} GP-отчёт. Верни JSON по схеме из system-промпта "
            "(gp_synthesis, problem_list, plan, safety_net, evidence_pmids). "
            "Не менее 2 safety-net триггеров. plan.action — максимум 5 задач, максимально конкретные. "
            "В evidence_pmids включай только PMID из списка evidence[].ref (те у которых source='pubmed')."
        ),
    }
    # Monthly review uses Opus for deeper trend synthesis over 90-day windows.
    if kind == "monthly":
        from ..config import get_settings
        gp_agent = GP_AGENT.clone(
            model=get_settings().synthesis_model,
            max_tokens=4500,
        )
        gp_payload["instruction"] = (
            "Составь месячный стратегический обзор (kind=monthly). Фокус: "
            "куда движемся за 30-90 дней, какие тренды лабов/метрик устойчивы, "
            "что из прошлых problem_list резолвилось, что осталось, что новое появилось. "
            "prior_reports в контексте — предыдущие weekly MDT, используй для ретроспективы. "
            "Верни JSON по той же схеме (gp_synthesis — 5-8 абзацев; problem_list обновлённый; "
            "plan.action — 3-5 СТРАТЕГИЧЕСКИХ задач на месяц; safety_net минимум 3)."
        )
    else:
        gp_agent = GP_AGENT
    gp_response = gp_agent.run(gp_payload)
    gp_raw = gp_response.raw
    # GP returns richer structure — parse from narrative-style JSON
    gp_parsed = _parse_gp_output(gp_response)

    # Step 5: persist — evidence_pmids already deduplicated upstream
    gp_cited = [p for p in gp_parsed.get("evidence_pmids", []) if p]
    all_evidence_keys = list(dict.fromkeys(pmids + gp_cited))
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

    # Coaching microtasks: each lifestyle agent can emit at most 1 recommendation.
    # We promote them directly to Task, deduplicating against open tasks with the
    # same title (so the same reminder doesn't accumulate day over day).
    _spawn_coaching_tasks(session, user, notes)

    return b


def _spawn_coaching_tasks(session: Session, user: User, notes: list[AgentResponse]) -> None:
    """Create at most 1 open task per lifestyle agent from today's recommendations.

    Deduplication rules:
    - Skip if an open task with the same title exists for this user.
    - Skip if the same agent already created an open task in the last 3 days
      (avoids chaining daily variants of the same advice).
    """
    from datetime import timedelta
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    for r in notes:
        if not r.recommendations:
            continue
        item = r.recommendations[0]  # we enforce max=1 in prompt
        title = (item.get("title") or "").strip()
        if not title:
            continue
        created_by = f"coach:{r.agent_name}"
        # Recent-dup check
        recent = session.exec(
            select(Task).where(
                Task.user_id == user.id,
                Task.created_by == created_by,
                Task.created_at >= three_days_ago,
                Task.status == "open",
            )
        ).first()
        if recent:
            continue
        # Title-dup check
        same = session.exec(
            select(Task).where(
                Task.user_id == user.id,
                Task.title == title,
                Task.status == "open",
            )
        ).first()
        if same:
            continue
        task = Task(
            user_id=user.id,
            created_by=created_by,
            title=title[:200],
            detail=item.get("detail", ""),
            priority=item.get("priority", "normal"),
            due=_parse_due(item.get("due_days")),
        )
        session.add(task)
    session.commit()


# --- helpers ---

def _prior_reports_for_retrospect(
    session: Session, user: User, *, limit: int = 5
) -> list[dict]:
    """Recent MDT reports (weekly) for the monthly retrospect. Compact — agents
    don't need full specialist notes, just problem_list and gp_synthesis snippets.
    """
    rows = session.exec(
        select(MdtReport)
        .where(MdtReport.user_id == user.id, MdtReport.kind != "monthly")
        .order_by(MdtReport.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "created_at": r.created_at.date().isoformat(),
            "gp_synthesis_excerpt": (r.gp_synthesis or "")[:800],
            "problem_list": r.problem_list,
            "safety_net": r.safety_net,
        }
        for r in rows
    ]


def _unify_evidence(
    pubmed_map: dict[str, list[str]],
    scholar_map: dict[str, list[dict]],
    session: Session,
) -> list[dict]:
    """Merge PubMed + Semantic Scholar hits into a single dedup'd reference list.

    Dedup rules:
    - Group by PMID when present (both sources may return the same paper with PMID).
      PubMed wins for metadata — its cached PubmedEvidence row has a fuller abstract.
    - When no PMID (Semantic Scholar-only), group by paperId (ss_id).
    - Keeps first-seen order so the GP sees the most relevant papers first.

    Returns: list of dicts with keys pmid|ss_id, title, journal, year, url, source.
    """
    from ..db import PubmedEvidence

    merged: dict[str, dict] = {}
    order: list[str] = []

    # PubMed first so it claims the PMID key
    pmid_set = {pmid for pmids in pubmed_map.values() for pmid in pmids if pmid}
    pm_rows: dict[str, PubmedEvidence] = {}
    if pmid_set:
        rows = session.exec(
            select(PubmedEvidence).where(PubmedEvidence.pmid.in_(list(pmid_set)))
        ).all()
        for row in rows:
            if row.pmid and row.title and row.title != "(no results)":
                pm_rows.setdefault(row.pmid, row)  # latest cached row per PMID

    for pmid in pmid_set:
        row = pm_rows.get(pmid)
        if not row:
            continue
        key = f"pmid:{pmid}"
        if key in merged:
            continue
        merged[key] = {
            "pmid": pmid,
            "ss_id": "",
            "title": row.title,
            "journal": row.journal,
            "year": row.pub_year,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source": "pubmed",
        }
        order.append(key)

    # Semantic Scholar fills gaps (papers not in PubMed, or with richer venue/citation info)
    for records in scholar_map.values():
        for r in records:
            if not r.get("title"):
                continue
            pmid = (r.get("pmid") or "").strip()
            ss_id = (r.get("ss_id") or "").strip()
            key = f"pmid:{pmid}" if pmid else f"ss:{ss_id}"
            if not key.endswith(":") and key in merged:
                continue  # already have this paper from PubMed — skip
            if not pmid and not ss_id:
                continue
            merged[key] = {
                "pmid": pmid,
                "ss_id": ss_id,
                "title": r["title"],
                "journal": r.get("journal", ""),
                "year": r.get("year"),
                "citations": r.get("citations", 0),
                "url": r.get("url", ""),
                "source": "semantic_scholar",
            }
            order.append(key)

    return [merged[k] for k in order if k in merged]


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
