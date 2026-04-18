"""FastAPI entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import get_settings
from .db import init_db
from .routes import auth, data, documents, medications, reports, tasks, sources, chat, meta, push, telegram, public, withings
from .scheduler.jobs import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
    # Auto-seed demo data on first launch so the product is immediately usable
    _auto_seed_if_empty()
    scheduler = start_scheduler()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        shutdown_scheduler(scheduler)


app = FastAPI(
    title="Consilium",
    version="0.1.0",
    description="Multi-agent personal health assistant",
    lifespan=lifespan,
)

# CORS — same-origin in production (Caddy handles it), open in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware — required by authlib for OAuth state/nonce handling
_settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=_settings.session_secret or "dev-only-insecure-secret-change-me",
    same_site="lax",
    https_only=_settings.domain != "localhost",
)

# Routers
app.include_router(meta.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(data.router, prefix="/data", tags=["data"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(withings.router, prefix="/sources/withings", tags=["withings"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(medications.router, prefix="/medications", tags=["medications"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(push.router, prefix="/push", tags=["push"])
app.include_router(telegram.router, prefix="/telegram", tags=["telegram"])
app.include_router(public.router, prefix="/public", tags=["public"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _auto_seed_if_empty() -> None:
    """Seed demo data on first start so product is usable immediately after login.

    Only runs if the DB has zero users (fresh install). Skipped silently otherwise.
    """
    from sqlmodel import Session, select
    from .db import User
    from .db.session import engine

    with Session(engine) as s:
        if s.exec(select(User)).first():
            return  # already has data
    try:
        from .seed import seed
        seed()
        logging.getLogger(__name__).info("Auto-seeded demo data for first launch")
    except Exception as e:
        logging.getLogger(__name__).warning("Auto-seed failed (non-fatal): %s", e)
