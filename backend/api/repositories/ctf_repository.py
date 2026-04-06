"""Repository operations for CTF sources and challenge catalog."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.api.db_models import Challenge, ChallengeFile, CTFSource, SolverRun
from backend.api.utils import utcnow

_SLUG_PATTERN = re.compile(r"[^a-z0-9-]+")




def slugify(value: str) -> str:
    base = value.strip().lower().replace("_", "-").replace(" ", "-")
    base = _SLUG_PATTERN.sub("-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    return base or "ctf"


def _ensure_unique_ctf_slug(session: Session, desired_slug: str, ctf_id: int | None = None) -> str:
    candidate = desired_slug
    suffix = 1
    while True:
        stmt = select(CTFSource).where(CTFSource.slug == candidate)
        existing = session.execute(stmt).scalar_one_or_none()
        if not existing or (ctf_id is not None and existing.id == ctf_id):
            return candidate
        suffix += 1
        candidate = f"{desired_slug}-{suffix}"


def list_ctf_sources(session: Session) -> list[tuple[CTFSource, int]]:
    stmt = (
        select(CTFSource, func.count(Challenge.id))
        .outerjoin(Challenge, Challenge.ctf_id == CTFSource.id)
        .group_by(CTFSource.id)
        .order_by(CTFSource.created_at.desc())
    )
    return list(session.execute(stmt).all())


def get_ctf_source(session: Session, ctf_id: int) -> CTFSource | None:
    return session.get(CTFSource, ctf_id)


def get_or_create_ctf_source(
    session: Session,
    *,
    name: str,
    base_url: str,
    auth_mode: str,
    challenges_root: str,
) -> CTFSource:
    stmt = select(CTFSource).where(CTFSource.name == name, CTFSource.base_url == base_url)
    existing = session.execute(stmt).scalar_one_or_none()
    if existing:
        existing.auth_mode = auth_mode
        existing.challenges_root = challenges_root
        existing.updated_at = utcnow()
        session.flush()
        return existing

    desired_slug = slugify(name)
    source = CTFSource(
        name=name,
        slug=_ensure_unique_ctf_slug(session, desired_slug),
        base_url=base_url,
        auth_mode=auth_mode,
        challenges_root=challenges_root,
        last_import_status="pending",
    )
    session.add(source)
    session.flush()
    return source


def set_import_status(
    session: Session,
    source: CTFSource,
    *,
    status: str,
    error: str = "",
) -> None:
    source.last_import_status = status
    source.last_import_error = error
    source.last_import_at = utcnow()
    source.updated_at = utcnow()
    session.flush()


def list_challenges(session: Session, ctf_id: int | None = None) -> list[Challenge]:
    stmt: Select[tuple[Challenge]] = select(Challenge).options(
        joinedload(Challenge.ctf_source),
        selectinload(Challenge.runs),
    )
    if ctf_id is not None:
        stmt = stmt.where(Challenge.ctf_id == ctf_id)
    stmt = stmt.order_by(Challenge.name.asc())
    return list(session.execute(stmt).scalars().all())


def get_challenge_by_id(session: Session, challenge_id: str) -> Challenge | None:
    stmt = (
        select(Challenge)
        .options(
            joinedload(Challenge.ctf_source),
            joinedload(Challenge.files),
            selectinload(Challenge.runs),
        )
        .where(Challenge.id == challenge_id)
    )
    return session.execute(stmt).unique().scalar_one_or_none()


def sync_challenge_with_run(
    session: Session,
    *,
    challenge_id: str,
    run: SolverRun,
) -> Challenge | None:
    challenge = get_challenge_by_id(session, challenge_id)
    if not challenge:
        return None

    challenge.state = run.status
    challenge.latest_run_id = run.id
    challenge.current_run_id = run.id if run.status in {"starting", "running"} else None
    challenge.latest_flag = run.flag
    challenge.latest_log_path = run.output_log_path or None
    challenge.latest_trace_id = run.latest_trace_id
    challenge.steering_log_path = run.steering_log_path or None
    challenge.started_at = run.started_at
    challenge.finished_at = run.finished_at
    challenge.updated_at = utcnow()
    session.flush()
    return challenge


def clear_challenge_session_data(session: Session, challenge_id: str) -> Challenge | None:
    challenge = get_challenge_by_id(session, challenge_id)
    if not challenge:
        return None

    challenge.state = "idle"
    challenge.latest_run_id = None
    challenge.current_run_id = None
    challenge.latest_flag = None
    challenge.latest_log_path = None
    challenge.latest_trace_id = None
    challenge.steering_log_path = None
    challenge.started_at = None
    challenge.finished_at = None
    challenge.updated_at = utcnow()
    session.flush()
    return challenge


def upsert_challenge(
    session: Session,
    *,
    source: CTFSource,
    external_id: int | None,
    name: str,
    challenge_slug: str,
    path: str,
    category: str,
    value: int,
    description: str,
    connection_info: str,
    has_distfiles: bool,
    distfile_count: int,
    solves: int,
) -> Challenge:
    challenge: Challenge | None = None

    if external_id is not None:
        stmt = select(Challenge).where(
            Challenge.ctf_id == source.id,
            Challenge.external_id == external_id,
        )
        challenge = session.execute(stmt).scalar_one_or_none()

    if challenge is None:
        stmt = select(Challenge).where(Challenge.ctf_id == source.id, Challenge.slug == challenge_slug)
        challenge = session.execute(stmt).scalar_one_or_none()

    now = utcnow()
    if challenge is None:
        challenge = Challenge(
            id=secrets.token_urlsafe(9),
            ctf_id=source.id,
            external_id=external_id,
            name=name,
            slug=challenge_slug,
            path=path,
            category=category,
            value=value,
            description=description,
            connection_info=connection_info,
            has_distfiles=has_distfiles,
            distfile_count=distfile_count,
            solves=solves,
            imported_at=now,
            updated_at=now,
        )
        session.add(challenge)
    else:
        challenge.external_id = external_id
        challenge.name = name
        challenge.slug = challenge_slug
        challenge.path = path
        challenge.category = category
        challenge.value = value
        challenge.description = description
        challenge.connection_info = connection_info
        challenge.has_distfiles = has_distfiles
        challenge.distfile_count = distfile_count
        challenge.solves = solves
        challenge.imported_at = now
        challenge.updated_at = now

    session.flush()
    return challenge


def replace_challenge_files(
    session: Session,
    *,
    challenge: Challenge,
    files: list[dict[str, Any]],
) -> None:
    challenge.files.clear()
    session.flush()

    for item in files:
        challenge.files.append(
            ChallengeFile(
                filename=str(item.get("filename") or ""),
                source_url=str(item.get("source_url") or ""),
                local_path=str(item.get("local_path") or ""),
                size_bytes=int(item.get("size_bytes") or 0),
            )
        )
    session.flush()
