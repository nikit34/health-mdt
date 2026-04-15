"""Scheduled jobs — daily brief, weekly MDT, Oura sync, task follow-up."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from ..agents.orchestrator import generate_daily_brief, run_mdt_consilium
from ..config import get_settings
from ..db import Task, User
from ..db.session import engine
from ..integrations.oura import fetch_oura_daily

log = logging.getLogger(__name__)


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    sched = BackgroundScheduler(timezone=settings.timezone)

    # 06:30 daily — sync Oura, then build brief
    sched.add_job(_daily_sync_and_brief, CronTrigger(hour=6, minute=30), id="daily_brief", replace_existing=True)

    # 08:00 Sunday — weekly MDT
    sched.add_job(_weekly_mdt, CronTrigger(day_of_week="sun", hour=8, minute=0), id="weekly_mdt", replace_existing=True)

    # 09:00 every day — task follow-up for stale tasks
    sched.add_job(_task_followup, CronTrigger(hour=9, minute=0), id="task_followup", replace_existing=True)

    # Every 6h — refresh Oura in case user sync missed morning
    sched.add_job(_oura_only, CronTrigger(minute=0, hour="*/6"), id="oura_refresh", replace_existing=True)

    sched.start()
    log.info("Scheduler started with %d jobs", len(sched.get_jobs()))
    return sched


def shutdown_scheduler(sched: BackgroundScheduler) -> None:
    try:
        sched.shutdown(wait=False)
    except Exception as e:
        log.warning("Scheduler shutdown error: %s", e)


def _for_each_user(fn) -> None:
    """Helper: iterate all users (single-user in PIN mode, multi in OAuth)."""
    with Session(engine) as s:
        users = s.exec(select(User)).all()
        for user in users:
            try:
                fn(s, user)
            except Exception as e:
                log.exception("Scheduled job failed for user %s: %s", user.id, e)


def _daily_sync_and_brief() -> None:
    settings = get_settings()
    if not settings.has_llm:
        log.info("Skip daily brief — no LLM key")
        return

    def _job(s, user):
        if settings.has_oura:
            try:
                fetch_oura_daily(s, user, since=(datetime.utcnow() - timedelta(days=2)).date())
            except Exception as e:
                log.warning("Daily Oura sync failed: %s", e)
        brief = generate_daily_brief(s, user)
        log.info("Daily brief created for user %s: id=%s", user.id, brief.id)

    _for_each_user(_job)


def _weekly_mdt() -> None:
    settings = get_settings()
    if not settings.has_llm:
        return

    def _job(s, user):
        report = run_mdt_consilium(s, user, kind="weekly", window_days=7)
        log.info("Weekly MDT created for user %s: id=%s", user.id, report.id)

    _for_each_user(_job)


def _task_followup() -> None:
    """Mark stale tasks (>7d open) for reminder — bot picks these up."""
    threshold = datetime.utcnow() - timedelta(days=7)
    with Session(engine) as s:
        stale = s.exec(
            select(Task).where(
                Task.status == "open",
                Task.created_at < threshold,
            )
        ).all()
        updated = 0
        for t in stale:
            last = t.last_reminded_at
            if last and (datetime.utcnow() - last) < timedelta(days=7):
                continue
            t.last_reminded_at = datetime.utcnow()
            s.add(t)
            updated += 1
        s.commit()
        if updated:
            log.info("Flagged %d stale tasks for follow-up", updated)


def _oura_only() -> None:
    settings = get_settings()
    if not settings.has_oura:
        return

    def _job(s, user):
        fetch_oura_daily(s, user, since=(datetime.utcnow() - timedelta(days=2)).date())

    _for_each_user(_job)
