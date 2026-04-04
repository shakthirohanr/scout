"""Database engine/session wiring for the modular API."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
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

    Base.metadata.create_all(bind=get_engine(settings))
