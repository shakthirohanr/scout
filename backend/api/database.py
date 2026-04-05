"""Database engine/session wiring for the modular API."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import Settings
from backend.run_config import REPO_ROOT


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


def resolve_database_url(settings: Settings) -> str:
    configured = settings.database_url or settings.postgres_url
    if configured:
        url = configured.strip()
        # SQLAlchemy defaults `postgresql://` to psycopg2; this project uses psycopg v3.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    sqlite_path = REPO_ROOT / ".ctf-agent.db"
    return f"sqlite+pysqlite:///{sqlite_path}"


@lru_cache(maxsize=4)
def _build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def get_engine(settings: Settings | None = None):
    resolved_settings = settings or Settings()
    return _build_engine(resolve_database_url(resolved_settings))


def get_session_factory(settings: Settings | None = None):
    return sessionmaker(
        bind=get_engine(settings),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database(settings: Settings | None = None) -> None:
    from backend.api import db_models  # noqa: F401

    engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)
    _apply_schema_updates(engine)


def _apply_schema_updates(engine) -> None:
    challenge_columns = {
        "state": "VARCHAR(32) NOT NULL DEFAULT 'idle'",
        "latest_run_id": "VARCHAR(64)",
        "current_run_id": "VARCHAR(64)",
        "latest_flag": "TEXT",
        "latest_log_path": "VARCHAR(2048)",
        "latest_trace_id": "VARCHAR(255)",
        "steering_log_path": "VARCHAR(2048)",
        "finished_at": "TIMESTAMP",
    }
    solver_run_columns = {
        "steering_log_path": "VARCHAR(2048) NOT NULL DEFAULT ''",
        "flag": "TEXT",
        "latest_trace_id": "VARCHAR(255)",
    }

    _ensure_columns(engine, "challenges", challenge_columns)
    _ensure_columns(engine, "solver_runs", solver_run_columns)


def _ensure_columns(engine, table_name: str, columns: dict[str, str]) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing_columns = {
        name: definition
        for name, definition in columns.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, definition in missing_columns.items():
            connection.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
            )
