"""Apple Health XML importer.

User exports via iOS: Health app → profile → Export All Health Data → export.zip.
Inside is export.xml. We stream-parse it (can be hundreds of MB) and upsert the most
clinically useful record types.
"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree
from sqlmodel import Session, select

from ..db import Metric, User

log = logging.getLogger(__name__)

# HK identifier → (our kind, unit, aggregate)
TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "HKQuantityTypeIdentifierStepCount": ("steps", "count", "sum_day"),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("active_calories", "kcal", "sum_day"),
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "bpm", "raw"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_hr", "bpm", "raw"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_sdnn", "ms", "raw"),
    "HKQuantityTypeIdentifierVO2Max": ("vo2max", "ml/kg/min", "raw"),
    "HKQuantityTypeIdentifierBodyMass": ("weight", "kg", "raw"),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("body_fat_pct", "%", "raw"),
    "HKQuantityTypeIdentifierRespiratoryRate": ("respiratory_rate", "bpm", "raw"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2", "%", "raw"),
    "HKQuantityTypeIdentifierBloodPressureSystolic": ("bp_systolic", "mmHg", "raw"),
    "HKQuantityTypeIdentifierBloodPressureDiastolic": ("bp_diastolic", "mmHg", "raw"),
    "HKCategoryTypeIdentifierSleepAnalysis": ("sleep_duration", "seconds", "sleep"),
}


def import_apple_health_xml(
    session: Session,
    user: User,
    archive_path: Path,
    *,
    since_days: int = 365,
) -> dict[str, int]:
    """Import from an export.zip or plain export.xml.

    Returns counts: {kind: n_inserted}. Idempotent per (user, ts, kind, source).
    """
    archive_path = Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(archive_path)

    cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400
    counts: dict[str, int] = {}

    # --- pick source stream ---
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            xml_name = next(
                (n for n in zf.namelist() if n.endswith("export.xml")),
                None,
            )
            if not xml_name:
                raise ValueError("export.xml not found in zip")
            with zf.open(xml_name) as f:
                _stream_parse(f, session, user.id, cutoff, counts)
    else:
        with archive_path.open("rb") as f:
            _stream_parse(f, session, user.id, cutoff, counts)

    session.commit()
    log.info("Apple Health import done: %s", counts)
    return counts


def _stream_parse(fp, session: Session, user_id: int, cutoff: float, counts: dict[str, int]) -> None:
    ctx = etree.iterparse(fp, events=("end",), tag="Record", recover=True)
    # Cache ts-kind tuples we've seen this session to dedupe before DB check
    seen: set[tuple[float, str]] = set()
    buffered = 0

    for _, el in ctx:
        try:
            hk_type = el.get("type", "")
            if hk_type not in TYPE_MAP:
                _clear(el)
                continue
            kind, unit, agg = TYPE_MAP[hk_type]
            start_date = el.get("startDate")
            value_s = el.get("value")
            if not start_date or value_s is None:
                _clear(el)
                continue
            try:
                ts = datetime.fromisoformat(start_date.replace(" +", "+").replace(" -", "-"))
            except ValueError:
                _clear(el)
                continue

            if ts.timestamp() < cutoff:
                _clear(el)
                continue

            # Category types (sleep): value is a string; convert to duration
            if agg == "sleep":
                end_s = el.get("endDate")
                if not end_s:
                    _clear(el)
                    continue
                try:
                    end_ts = datetime.fromisoformat(end_s.replace(" +", "+").replace(" -", "-"))
                except ValueError:
                    _clear(el)
                    continue
                fval = (end_ts - ts).total_seconds()
                if fval <= 0:
                    _clear(el)
                    continue
            else:
                try:
                    fval = float(value_s)
                except ValueError:
                    _clear(el)
                    continue

            dedupe_key = (ts.timestamp(), kind)
            if dedupe_key in seen:
                _clear(el)
                continue
            seen.add(dedupe_key)

            session.add(Metric(
                user_id=user_id,
                ts=ts.replace(tzinfo=None),  # store naive for simplicity
                source="apple_health",
                kind=kind,
                value=fval,
                unit=unit,
            ))
            counts[kind] = counts.get(kind, 0) + 1
            buffered += 1
            if buffered >= 500:
                session.commit()
                buffered = 0
        finally:
            _clear(el)


def _clear(el) -> None:
    """Free the element to keep memory bounded during streaming."""
    el.clear()
    while el.getprevious() is not None:
        del el.getparent()[0]
