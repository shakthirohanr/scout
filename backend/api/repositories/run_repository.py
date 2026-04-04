"""Repository operations for solver run persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.db_models import SolverRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def upsert_run(session: Session, payload: dict[str, Any]) -> SolverRun:
    run_id = str(payload["id"])
    existing = session.get(SolverRun, run_id)
    command_json = json.dumps(payload.get("command", []), ensure_ascii=True)
    trace_ids_json = json.dumps(payload.get("trace_ids", []), ensure_ascii=True)

    if existing is None:
        existing = SolverRun(
            id=run_id,
            challenge_id=payload.get("challenge_id"),
            mode=str(payload.get("mode") or "solve"),
            status=str(payload.get("status") or "starting"),
            command_json=command_json,
            workdir=str(payload.get("workdir") or ""),
            pid=payload.get("pid"),
            output_log_path=str(payload.get("output_log_path") or ""),
            trace_ids_json=trace_ids_json,
            exit_code=payload.get("exit_code"),
            created_at=payload.get("created_at") or _utcnow(),
            started_at=payload.get("started_at"),
            finished_at=payload.get("finished_at"),
            updated_at=_utcnow(),
        )
        session.add(existing)
    else:
        existing.challenge_id = payload.get("challenge_id")
        existing.mode = str(payload.get("mode") or existing.mode)
        existing.status = str(payload.get("status") or existing.status)
        existing.command_json = command_json
        existing.workdir = str(payload.get("workdir") or existing.workdir)
        existing.pid = payload.get("pid")
        existing.output_log_path = str(payload.get("output_log_path") or existing.output_log_path)
        existing.trace_ids_json = trace_ids_json
        existing.exit_code = payload.get("exit_code")
        existing.started_at = payload.get("started_at")
        existing.finished_at = payload.get("finished_at")
        existing.updated_at = _utcnow()

    session.flush()
    return existing


def list_runs(session: Session, limit: int = 200) -> list[SolverRun]:
    stmt = select(SolverRun).order_by(SolverRun.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())
