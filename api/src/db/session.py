"""SQLite session factory — zero-config."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from ..config import get_settings

_settings = get_settings()

# sqlite:///data/health.db → resolve relative to working dir
db_path = Path(_settings.database_url.replace("sqlite:///", ""))
db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables if they don't exist. Called on API startup.

    Also runs lightweight additive migrations: for SQLite, `create_all` doesn't
    touch existing tables, so new columns added to models aren't automatically
    applied to upgraded deployments. We inspect PRAGMA and ALTER TABLE as needed.
    """
    # Import models so SQLModel registers them
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _apply_additive_migrations()


# Additive column migrations for SQLite. Keep this list append-only; entries
# are idempotent so re-running the app after a rollback is safe.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    # (table, column, definition)
    ("user", "withings_user_id", "TEXT"),
    ("user", "withings_access_token", "TEXT"),
    ("user", "withings_refresh_token", "TEXT"),
    ("user", "withings_expires_at", "TIMESTAMP"),
]


def _apply_additive_migrations() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, definition in _ADDITIVE_COLUMNS:
            try:
                existing_cols = {c["name"] for c in insp.get_columns(table)}
            except Exception:
                # Table doesn't exist yet — create_all will have just made it with the column.
                continue
            if column in existing_cols:
                continue
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN {column} {definition}'))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
