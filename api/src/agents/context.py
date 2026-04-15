"""Builds context bundles for agents.

We hand each agent a compact JSON snapshot: recent metrics aggregated to daily,
last N check-ins, valid lab results (with freshness flagged), and problem-list context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import mean, median

from sqlmodel import Session, select

from ..db import Checkin, LabResult, Metric, Task, User


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

    # === Labs with validity ===
    labs_stmt = select(LabResult).where(LabResult.user_id == user.id).order_by(LabResult.drawn_at.desc())
    labs: list[dict] = []
    for lr in session.exec(labs_stmt).all()[:50]:
        window = VALIDITY_DAYS.get(lr.panel, VALIDITY_DAYS["default"])
        age_days = (today - lr.drawn_at).days
        labs.append({
            "panel": lr.panel,
            "analyte": lr.analyte,
            "value": lr.value,
            "unit": lr.unit,
            "ref_low": lr.ref_low,
            "ref_high": lr.ref_high,
            "flag": lr.flag,
            "drawn_at": lr.drawn_at.isoformat(),
            "age_days": age_days,
            "valid": age_days <= window,
            "validity_window_days": window,
        })

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
        notes=notes,
    )


def _age(birthdate: date) -> int:
    today = date.today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
