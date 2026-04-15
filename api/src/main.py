"""FastAPI entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routes import auth, data, documents, reports, tasks, sources, chat, meta
from .scheduler.jobs import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_db()
    scheduler = start_scheduler()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        shutdown_scheduler(scheduler)


app = FastAPI(
    title="health-mdt",
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

# Routers
app.include_router(meta.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(data.router, prefix="/data", tags=["data"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
