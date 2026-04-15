"""Oura API v2 client — pulls daily summaries for sleep, readiness, HRV, activity."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..db import Metric, User

log = logging.getLogger(__name__)

BASE = "https://api.ouraring.com/v2/usercollection"

# Map Oura endpoint → (list of (json_path, metric_kind, unit))
MAPPINGS = {
    "daily_sleep": [
        ("score", "sleep_score", "score"),
    ],
    "sleep": [
        ("total_sleep_duration", "sleep_duration", "seconds"),
        ("efficiency", "sleep_efficiency", "percent"),
        ("latency", "sleep_latency", "seconds"),
        ("rem_sleep_duration", "sleep_rem", "seconds"),
        ("deep_sleep_duration", "sleep_deep", "seconds"),
        ("average_hrv", "hrv_rmssd_night", "ms"),
        ("lowest_heart_rate", "resting_hr", "bpm"),
        ("average_heart_rate", "avg_hr_night", "bpm"),
    ],
    "daily_activity": [
        ("steps", "steps", "count"),
        ("active_calories", "active_calories", "kcal"),
        ("equivalent_walking_distance", "walking_distance", "m"),
        ("score", "activity_score", "score"),
    ],
    "daily_readiness": [
        ("score", "readiness_score", "score"),
    ],
    "daily_stress": [
        ("stress_high", "stress_high_seconds", "seconds"),
        ("recovery_high", "recovery_high_seconds", "seconds"),
    ],
}


def _get(client: httpx.Client, path: str, params: dict) -> list[dict]:
    url = f"{BASE}/{path}"
    resp = client.get(url, params=params, timeout=30)
    if resp.status_code == 401:
        raise RuntimeError("Oura API 401 — token invalid or revoked")
    resp.raise_for_status()
    return resp.json().get("data", [])


def _extract_ts(doc: dict, endpoint: str) -> datetime | None:
    """Oura docs have 'day' (YYYY-MM-DD) and sometimes 'bedtime_start'."""
    if "bedtime_start" in doc and doc["bedtime_start"]:
        try:
            return datetime.fromisoformat(doc["bedtime_start"].replace("Z", "+00:00"))
        except ValueError:
            pass
    if "day" in doc:
        try:
            return datetime.fromisoformat(doc["day"])
        except ValueError:
            pass
    if "timestamp" in doc:
        try:
            return datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def fetch_oura_daily(
    session: Session,
    user: User,
    *,
    since: date | None = None,
    until: date | None = None,
) -> dict[str, int]:
    """Pull and upsert Oura data into Metric table. Idempotent per (ts, kind, source)."""
    settings = get_settings()
    if not settings.has_oura:
        return {"error": 0, "skipped": "no_token"}

    until = until or date.today()
    since = since or (until - timedelta(days=14))

    headers = {"Authorization": f"Bearer {settings.oura_personal_access_token}"}
    counts = {"inserted": 0, "skipped_existing": 0, "endpoints": 0}

    with httpx.Client(headers=headers) as client:
        for endpoint, fields in MAPPINGS.items():
            try:
                docs = _get(
                    client,
                    endpoint,
                    {"start_date": since.isoformat(), "end_date": until.isoformat()},
                )
            except Exception as e:
                log.warning("Oura %s fetch failed: %s", endpoint, e)
                continue
            counts["endpoints"] += 1
            for doc in docs:
                ts = _extract_ts(doc, endpoint)
                if not ts:
                    continue
                # "contributors" / "details" sometimes wrap the useful fields
                flat: dict[str, Any] = {**doc}
                for sub in ("contributors", "details", "heart_rate"):
                    if isinstance(doc.get(sub), dict):
                        flat.update(doc[sub])
                for json_key, kind, unit in fields:
                    val = flat.get(json_key)
                    if val is None:
                        continue
                    try:
                        fval = float(val)
                    except (TypeError, ValueError):
                        continue
                    if _already_stored(session, user.id, ts, kind, "oura"):
                        counts["skipped_existing"] += 1
                        continue
                    session.add(Metric(
                        user_id=user.id,
                        ts=ts,
                        source="oura",
                        kind=kind,
                        value=fval,
                        unit=unit,
                        meta={"oura_endpoint": endpoint},
                    ))
                    counts["inserted"] += 1
    session.commit()
    log.info("Oura sync done: %s", counts)
    return counts


def _already_stored(session: Session, user_id: int, ts: datetime, kind: str, source: str) -> bool:
    stmt = (
        select(Metric.id)
        .where(
            Metric.user_id == user_id,
            Metric.ts == ts,
            Metric.kind == kind,
            Metric.source == source,
        )
        .limit(1)
    )
    return session.exec(stmt).first() is not None
