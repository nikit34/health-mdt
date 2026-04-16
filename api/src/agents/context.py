"""Builds context bundles for agents.

We hand each agent a compact JSON snapshot: recent metrics aggregated to daily,
last N check-ins, valid lab results (with freshness flagged), and problem-list context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import mean, median

from sqlmodel import Session, select

from ..db import Checkin, LabResult, Medication, Metric, Task, User


# Clinical validity windows (days) — kept here so they're easy to tune
VALIDITY_DAYS = {
    "cbc": 90,
    "cmp": 180,
    "lipids": 365,
    "thyroid": 180,
    "hba1c": 120,
    "glucose_fasting": 120,
    "vitamin_d": 365,
    "ferritin": 180,
    "b12": 180,
    "default": 180,
}


@dataclass
class ContextBundle:
    user: dict
    today: date
    window_days: int
    metrics: dict = field(default_factory=dict)  # kind -> summary dict
    labs: list[dict] = field(default_factory=list)
    checkins: list[dict] = field(default_factory=list)
    open_tasks: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "today": self.today.isoformat(),
            "window_days": self.window_days,
            "metrics": self.metrics,
            "labs": self.labs,
            "checkins": self.checkins,
            "open_tasks": self.open_tasks,
            "medications": self.medications,
            "notes": self.notes,
        }


def build_context(
    session: Session,
    user: User,
    *,
    window_days: int = 7,
    today: date | None = None,
) -> ContextBundle:
    today = today or date.today()
    since = datetime.combine(today - timedelta(days=window_days), datetime.min.time())

    # === Metrics: aggregate per-kind over the window ===
    metrics_stmt = select(Metric).where(
        Metric.user_id == user.id, Metric.ts >= since
    )
    raw: dict[str, list[tuple[datetime, float]]] = {}
    for m in session.exec(metrics_stmt).all():
        raw.setdefault(m.kind, []).append((m.ts, m.value))

    metrics_summary: dict[str, dict] = {}
    for kind, points in raw.items():
        vals = [v for _, v in points]
        if not vals:
            continue
        # Also compute 30-day baseline for trend analysis
        since30 = datetime.combine(today - timedelta(days=30), datetime.min.time())
        baseline_vals = [
            m.value
            for m in session.exec(
                select(Metric).where(
                    Metric.user_id == user.id,
                    Metric.kind == kind,
                    Metric.ts >= since30,
                    Metric.ts < since,
                )
            ).all()
        ]
        summary = {
            "n": len(vals),
            "latest": vals[-1] if vals else None,
            "mean": round(mean(vals), 2),
            "median": round(median(vals), 2),
            "min": min(vals),
            "max": max(vals),
            "daily_points": [
                {"date": ts.date().isoformat(), "value": round(v, 2)}
                for ts, v in points[-window_days:]
            ],
        }
        if baseline_vals:
            b_mean = mean(baseline_vals)
            delta_pct = ((summary["mean"] - b_mean) / b_mean * 100) if b_mean else 0.0
            summary["baseline_30d_mean"] = round(b_mean, 2)
            summary["delta_pct_vs_baseline"] = round(delta_pct, 1)
        metrics_summary[kind] = summary

    # === Labs: latest value per (panel, analyte) + time-series for trend view ===
    # Agents care about the most recent valid value AND how it's moving. A one-off
    # HbA1c of 6.2 is different from a trajectory 5.9 → 6.1 → 6.3.
    labs_stmt = (
        select(LabResult)
        .where(LabResult.user_id == user.id)
        .order_by(LabResult.drawn_at.desc())
    )
    all_rows = session.exec(labs_stmt).all()

    # Group by (panel, analyte); build latest + history (up to 5 most recent)
    by_analyte: dict[tuple[str, str], list[LabResult]] = {}
    for lr in all_rows:
        by_analyte.setdefault((lr.panel, lr.analyte), []).append(lr)

    labs: list[dict] = []
    for (panel, analyte), rows in by_analyte.items():
        rows_sorted = sorted(rows, key=lambda r: r.drawn_at, reverse=True)
        latest = rows_sorted[0]
        window = VALIDITY_DAYS.get(panel, VALIDITY_DAYS["default"])
        age_days = (today - latest.drawn_at).days

        history = [
            {"drawn_at": r.drawn_at.isoformat(), "value": r.value, "flag": r.flag}
            for r in rows_sorted[:5]
        ]
        trend = _compute_trend(history)

        labs.append({
            "panel": panel,
            "analyte": analyte,
            "value": latest.value,
            "unit": latest.unit,
            "ref_low": latest.ref_low,
            "ref_high": latest.ref_high,
            "flag": latest.flag,
            "drawn_at": latest.drawn_at.isoformat(),
            "age_days": age_days,
            "valid": age_days <= window,
            "validity_window_days": window,
            "history": history if len(history) > 1 else [],
            "trend": trend,  # 'rising' | 'falling' | 'stable' | None
            "n_measurements": len(rows),
        })
    # Keep first 50 to bound payload; already grouped so this is analyte-level
    labs.sort(key=lambda d: d["drawn_at"], reverse=True)
    labs = labs[:50]

    # === Check-ins ===
    ci_stmt = (
        select(Checkin)
        .where(Checkin.user_id == user.id, Checkin.ts >= since)
        .order_by(Checkin.ts.desc())
    )
    checkins = [
        {
            "ts": c.ts.isoformat(timespec="minutes"),
            "text": c.text,
            "mood": c.mood,
            "energy": c.energy,
            "sleep_quality": c.sleep_quality,
            "tags": c.tags,
        }
        for c in session.exec(ci_stmt).all()
    ]

    # === Open tasks (so agents don't duplicate) ===
    t_stmt = select(Task).where(Task.user_id == user.id, Task.status == "open")
    open_tasks = [
        {
            "id": t.id,
            "title": t.title,
            "priority": t.priority,
            "due": t.due.isoformat() if t.due else None,
            "created_by": t.created_by,
            "age_days": (datetime.utcnow() - t.created_at).days,
        }
        for t in session.exec(t_stmt).all()
    ]

    # === Medications (active + recently stopped) ===
    # Recently-stopped meds are useful context: a metric change right after stopping
    # a medication is important signal. We cap to the last 10 records.
    med_stmt = select(Medication).where(Medication.user_id == user.id).order_by(Medication.started_on.desc())
    medications: list[dict] = []
    for m in session.exec(med_stmt).all()[:10]:
        active = not m.stopped_on or m.stopped_on >= today
        medications.append({
            "name": m.name,
            "dose": m.dose,
            "frequency": m.frequency,
            "started_on": m.started_on.isoformat() if m.started_on else None,
            "stopped_on": m.stopped_on.isoformat() if m.stopped_on else None,
            "status": "active" if active else "stopped",
            "notes": m.notes,
        })

    notes: list[str] = []
    if not metrics_summary:
        notes.append("Нет метрик за окно — предложи пользователю подключить Oura / загрузить Apple Health.")
    if not labs:
        notes.append("Нет лабораторных данных — часть выводов будет ограничена.")

    user_dict = {
        "name": user.name,
        "age": _age(user.birthdate) if user.birthdate else None,
        "sex": user.sex,
        "height_cm": user.height_cm,
        "weight_kg": user.weight_kg,
        "context": user.context,
    }

    return ContextBundle(
        user=user_dict,
        today=today,
        window_days=window_days,
        metrics=metrics_summary,
        labs=labs,
        checkins=checkins,
        open_tasks=open_tasks,
        medications=medications,
        notes=notes,
    )


def _age(birthdate: date) -> int:
    today = date.today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def _compute_trend(history: list[dict]) -> str | None:
    """From the last few measurements, classify direction.

    Simple but useful: compare most-recent value to mean of prior 2+ values.
    A 5% swing counts as rising/falling; below that we call it stable.
    Returns None when there are <2 points.
    """
    if len(history) < 2:
        return None
    # history is newest-first
    latest = history[0]["value"]
    prior = [h["value"] for h in history[1:4]]  # up to 3 prior points
    if not prior:
        return None
    base = mean(prior)
    if base == 0:
        return None
    delta = (latest - base) / abs(base)
    if delta > 0.05:
        return "rising"
    if delta < -0.05:
        return "falling"
    return "stable"
