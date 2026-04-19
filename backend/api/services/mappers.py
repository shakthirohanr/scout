"""Mapping helpers from ORM models to API payload dictionaries."""

from __future__ import annotations

from datetime import datetime

from backend.api.db_models import Challenge, CTFSource, SolverRun
from backend.api.repositories.run_repository import ACTIVE_RUN_STATUSES


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def ctf_source_to_dict(source: CTFSource, challenge_count: int = 0) -> dict[str, object]:
    return {
        "id": source.id,
        "name": source.name,
        "slug": source.slug,
        "base_url": source.base_url,
        "auth_mode": source.auth_mode,
        "challenges_root": source.challenges_root,
        "challenge_count": challenge_count,
        "last_import_at": iso_or_none(source.last_import_at),
        "last_import_status": source.last_import_status,
        "last_import_error": source.last_import_error,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
    }


def challenge_to_dict(challenge: Challenge) -> dict[str, object]:
    active_run_ids = [run.id for run in challenge.runs if run.status in ACTIVE_RUN_STATUSES]
    return {
        "id": challenge.id,
        "ctf_id": challenge.ctf_id,
        "ctf_name": challenge.ctf_source.name if challenge.ctf_source else "unknown",
        "name": challenge.name,
        "path": challenge.path,
        "category": challenge.category,
        "value": challenge.value,
        "description": challenge.description,
        "connection_info": challenge.connection_info,
        "has_distfiles": challenge.has_distfiles,
        "distfile_count": challenge.distfile_count,
        "state": challenge.state,
        "run_count": len(challenge.runs),
        "latest_run_id": challenge.latest_run_id,
        "current_run_id": challenge.current_run_id,
        "active_run_ids": active_run_ids,
        "latest_flag": challenge.latest_flag,
        "latest_log_path": challenge.latest_log_path,
        "latest_trace_id": challenge.latest_trace_id,
        "steering_log_path": challenge.steering_log_path,
        "started_at": iso_or_none(challenge.started_at),
        "finished_at": iso_or_none(challenge.finished_at),
        "updated_at": iso_or_none(challenge.updated_at),
    }


def solver_run_to_dict(run: SolverRun) -> dict[str, object]:
    import json

    return {
        "run_id": run.id,
        "challenge_id": run.challenge_id,
        "mode": run.mode,
        "status": run.status,
        "command": json.loads(run.command_json or "[]"),
        "workdir": run.workdir,
        "pid": run.pid,
        "output_log_path": run.output_log_path,
        "steering_log_path": run.steering_log_path,
        "flag": run.flag,
        "latest_trace_id": run.latest_trace_id,
        "trace_ids": json.loads(run.trace_ids_json or "[]"),
        "exit_code": run.exit_code,
        "created_at": iso_or_none(run.created_at),
        "started_at": iso_or_none(run.started_at),
        "finished_at": iso_or_none(run.finished_at),
    }
