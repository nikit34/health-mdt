"""Withings API v2 client — OAuth2, scale + BP + sleep + body composition.

Setup (one-time for the instance owner):
  1. Register at https://developer.withings.com → create an app (Public Cloud).
  2. Redirect URI: https://<your-domain>/api/sources/withings/callback
     (for localhost: http://localhost/api/sources/withings/callback)
  3. Put client_id / client_secret into .env:
       WITHINGS_CLIENT_ID=...
       WITHINGS_CLIENT_SECRET=...
  4. Users then hit /sources/withings/connect which starts the OAuth flow.

Withings specifics worth knowing:
- Access token TTL is ~3 hours. Refresh tokens rotate on every use (old one invalidated).
  So we must persist the *new* refresh_token after each refresh, else user gets locked out.
- All endpoints accept POST with form-urlencoded body, not JSON. Action goes in body.
- Measure types are opaque integers — see MEASURE_TYPES below.
- Sleep + activity summaries are separate endpoints from point-in-time measures.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..db import Metric, User

log = logging.getLogger(__name__)

AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"
API_BASE = "https://wbsapi.withings.net"

# OAuth scopes — keep minimal. metrics covers scale + BP + ECG; info covers profile.
OAUTH_SCOPE = "user.metrics,user.info,user.activity"

# Withings measure type → (metric_kind, unit, convert_fn or None)
# Reference: https://developer.withings.com/api-reference/#operation/measure-getmeas
# `value` in Withings raw form is an integer; actual value = value * 10^unit (field).
MEASURE_TYPES: dict[int, tuple[str, str]] = {
    1:  ("weight", "kg"),
    4:  ("height", "m"),
    5:  ("fat_free_mass", "kg"),
    6:  ("body_fat_pct", "percent"),
    8:  ("fat_mass", "kg"),
    9:  ("bp_diastolic", "mmHg"),
    10: ("bp_systolic", "mmHg"),
    11: ("pulse_during_bp", "bpm"),
    12: ("body_temperature", "celsius"),
    54: ("spo2", "percent"),
    71: ("body_temperature_skin", "celsius"),
    73: ("skin_temperature", "celsius"),
    76: ("muscle_mass", "kg"),
    77: ("hydration", "kg"),
    88: ("bone_mass", "kg"),
    91: ("pulse_wave_velocity", "m_per_s"),  # arterial stiffness — key CV marker
    123: ("vo2max", "ml_per_kg_min"),
    135: ("qrs_interval", "ms"),
    136: ("pr_interval", "ms"),
    137: ("qt_interval", "ms"),
    138: ("corrected_qt_interval", "ms"),
}


# --- Public API ---

def build_authorize_url(state: str, redirect_uri: str) -> str:
    """Return the URL to redirect the user to for OAuth consent."""
    s = get_settings()
    params = {
        "response_type": "code",
        "client_id": s.withings_client_id,
        "scope": OAUTH_SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    from urllib.parse import urlencode
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """Exchange auth code for access + refresh tokens. Returns the full token payload."""
    s = get_settings()
    data = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": s.withings_client_id,
        "client_secret": s.withings_client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(TOKEN_URL, data=data)
    _raise_for_withings_error(resp, context="token_exchange")
    body = resp.json().get("body") or {}
    return body


def refresh_access_token(refresh_token: str) -> dict:
    """Swap refresh_token for a new access + refresh pair.

    IMPORTANT: Withings rotates refresh_token — the old one becomes invalid
    immediately. Caller MUST persist the new refresh_token.
    """
    s = get_settings()
    data = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": s.withings_client_id,
        "client_secret": s.withings_client_secret,
        "refresh_token": refresh_token,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(TOKEN_URL, data=data)
    _raise_for_withings_error(resp, context="token_refresh")
    return resp.json().get("body") or {}


def persist_token(session: Session, user: User, token_payload: dict) -> None:
    """Write access + refresh + expiry + withings user_id into User."""
    now = datetime.utcnow()
    expires_in = int(token_payload.get("expires_in", 0))
    user.withings_access_token = token_payload.get("access_token") or ""
    user.withings_refresh_token = token_payload.get("refresh_token") or user.withings_refresh_token
    user.withings_expires_at = now + timedelta(seconds=expires_in - 60)  # 60s safety margin
    withings_uid = token_payload.get("userid") or token_payload.get("user_id")
    if withings_uid:
        user.withings_user_id = str(withings_uid)
    session.add(user)
    session.commit()
    session.refresh(user)


def _ensure_fresh_token(session: Session, user: User) -> str | None:
    """Return a valid access token, refreshing if expired. None if user not connected."""
    if not user.withings_access_token:
        return None
    now = datetime.utcnow()
    if user.withings_expires_at and user.withings_expires_at > now:
        return user.withings_access_token
    if not user.withings_refresh_token:
        return None
    try:
        new_tokens = refresh_access_token(user.withings_refresh_token)
    except Exception as e:
        log.warning("Withings refresh failed for user %s: %s", user.id, e)
        return None
    persist_token(session, user, new_tokens)
    return user.withings_access_token


def disconnect(session: Session, user: User) -> None:
    """Clear Withings OAuth state for this user."""
    user.withings_access_token = None
    user.withings_refresh_token = None
    user.withings_expires_at = None
    user.withings_user_id = None
    session.add(user)
    session.commit()


# --- Data pulls ---

def fetch_withings(
    session: Session,
    user: User,
    *,
    since: date | None = None,
    until: date | None = None,
) -> dict[str, Any]:
    """Pull measures + sleep + activity for `user`, upsert as Metric rows.

    Returns a counts dict for UI feedback.
    """
    s = get_settings()
    if not s.has_withings:
        return {"error": "withings_app_not_configured"}
    token = _ensure_fresh_token(session, user)
    if not token:
        return {"error": "user_not_connected"}

    until = until or date.today()
    since = since or (until - timedelta(days=14))

    counts = {"inserted": 0, "skipped_existing": 0, "endpoints": 0}

    with httpx.Client(timeout=20, headers={"Authorization": f"Bearer {token}"}) as client:
        counts["endpoints"] += _pull_measures(client, session, user, since, until, counts)
        counts["endpoints"] += _pull_sleep(client, session, user, since, until, counts)
        counts["endpoints"] += _pull_activity(client, session, user, since, until, counts)

    session.commit()
    log.info("Withings sync done for user %s: %s", user.id, counts)
    return counts


def _pull_measures(
    client: httpx.Client, session: Session, user: User,
    since: date, until: date, counts: dict,
) -> int:
    """Point-in-time measures: weight, BP, body comp."""
    start_ts = int(datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.combine(until, datetime.max.time(), tzinfo=timezone.utc).timestamp())
    try:
        resp = client.post(
            f"{API_BASE}/measure",
            data={
                "action": "getmeas",
                "startdate": start_ts,
                "enddate": end_ts,
                "category": 1,  # 1 = real measures, 2 = user objectives — we want 1
            },
        )
        _raise_for_withings_error(resp, context="getmeas")
    except Exception as e:
        log.warning("Withings getmeas failed: %s", e)
        return 0

    body = resp.json().get("body") or {}
    groups = body.get("measuregrps", []) or []
    for grp in groups:
        ts = datetime.fromtimestamp(grp.get("date", 0), tz=timezone.utc).replace(tzinfo=None)
        for m in grp.get("measures", []) or []:
            mtype = m.get("type")
            mapping = MEASURE_TYPES.get(mtype)
            if not mapping:
                continue
            kind, unit = mapping
            raw_value = m.get("value")
            unit_exp = m.get("unit", 0)
            if raw_value is None:
                continue
            try:
                fval = float(raw_value) * (10 ** int(unit_exp))
            except (TypeError, ValueError):
                continue
            if _already_stored(session, user.id, ts, kind, "withings"):
                counts["skipped_existing"] += 1
                continue
            session.add(Metric(
                user_id=user.id, ts=ts, source="withings",
                kind=kind, value=fval, unit=unit,
                meta={"withings_grpid": grp.get("grpid"), "withings_type": mtype},
            ))
            counts["inserted"] += 1
    return 1


def _pull_sleep(
    client: httpx.Client, session: Session, user: User,
    since: date, until: date, counts: dict,
) -> int:
    """Nightly sleep summary — Withings Sleep Mat or Scanwatch."""
    try:
        resp = client.post(
            f"{API_BASE}/v2/sleep",
            data={
                "action": "getsummary",
                "startdateymd": since.isoformat(),
                "enddateymd": until.isoformat(),
                "data_fields": ",".join([
                    "total_sleep_time", "sleep_efficiency", "sleep_latency",
                    "rem_sleepduration", "deepsleepduration", "lightsleepduration",
                    "hr_average", "hr_min", "hr_max",
                    "rr_average", "rr_min", "rr_max",
                ]),
            },
        )
        _raise_for_withings_error(resp, context="sleep_summary")
    except Exception as e:
        log.warning("Withings sleep summary failed: %s", e)
        return 0
    body = resp.json().get("body") or {}
    rows = body.get("series", []) or []
    for row in rows:
        ts_raw = row.get("date") or row.get("startdate")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue
        elif isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc).replace(tzinfo=None)
        else:
            continue
        d = row.get("data") or {}
        mappings = [
            ("total_sleep_time", "sleep_duration", "seconds"),
            ("sleep_efficiency", "sleep_efficiency", "percent"),
            ("sleep_latency", "sleep_latency", "seconds"),
            ("rem_sleepduration", "sleep_rem", "seconds"),
            ("deepsleepduration", "sleep_deep", "seconds"),
            ("hr_average", "avg_hr_night", "bpm"),
            ("hr_min", "resting_hr", "bpm"),
            ("rr_average", "respiratory_rate_night", "bpm"),
        ]
        for api_field, kind, unit in mappings:
            val = d.get(api_field)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            if _already_stored(session, user.id, ts, kind, "withings"):
                counts["skipped_existing"] += 1
                continue
            session.add(Metric(
                user_id=user.id, ts=ts, source="withings",
                kind=kind, value=fval, unit=unit,
                meta={"withings_sleep_summary": True},
            ))
            counts["inserted"] += 1
    return 1


def _pull_activity(
    client: httpx.Client, session: Session, user: User,
    since: date, until: date, counts: dict,
) -> int:
    """Daily activity totals — steps, calories, distance."""
    try:
        resp = client.post(
            f"{API_BASE}/v2/measure",
            data={
                "action": "getactivity",
                "startdateymd": since.isoformat(),
                "enddateymd": until.isoformat(),
                "data_fields": "steps,distance,calories,elevation,active",
            },
        )
        _raise_for_withings_error(resp, context="getactivity")
    except Exception as e:
        log.warning("Withings activity failed: %s", e)
        return 0
    body = resp.json().get("body") or {}
    rows = body.get("activities", []) or []
    for row in rows:
        day_str = row.get("date")
        if not day_str:
            continue
        try:
            ts = datetime.fromisoformat(day_str)
        except ValueError:
            continue
        mappings = [
            ("steps", "steps", "count"),
            ("distance", "walking_distance", "m"),
            ("calories", "active_calories", "kcal"),
            ("elevation", "elevation", "m"),
        ]
        for api_field, kind, unit in mappings:
            val = row.get(api_field)
            if val is None:
                continue
            try:
                fval = float(val)
            except (TypeError, ValueError):
                continue
            if _already_stored(session, user.id, ts, kind, "withings"):
                counts["skipped_existing"] += 1
                continue
            session.add(Metric(
                user_id=user.id, ts=ts, source="withings",
                kind=kind, value=fval, unit=unit,
                meta={"withings_activity": True},
            ))
            counts["inserted"] += 1
    return 1


# --- Helpers ---

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


def _raise_for_withings_error(resp: httpx.Response, *, context: str) -> None:
    """Withings returns HTTP 200 even for errors — check `status` field in JSON body.

    Status codes: 0 = success; everything else = error (e.g. 401 = invalid token).
    """
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")
    if status != 0:
        raise RuntimeError(f"Withings {context} error: status={status} body={data}")
