from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from backend.api.repositories.run_repository import ACTIVE_RUN_STATUSES
from backend.api.utils import utcnow
from backend.log_reader import TraceSummary, list_trace_summaries

__all__ = ["TERMINAL_TRACE_STATUS_TO_RUN_STATUS", "snapshot_persisted_run"]

TERMINAL_TRACE_STATUS_TO_RUN_STATUS = {
    "solved": "solved",
    "gave_up": "gave_up",
    "cancelled": "cancelled",
    "error": "failed",
}


def _is_pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _timestamp_or_zero(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def _sort_trace_summaries_by_recency(summaries: list[TraceSummary]) -> list[TraceSummary]:
    return sorted(
        summaries,
        key=lambda summary: _timestamp_or_zero(summary.updated_at),
        reverse=True,
    )


def _build_trace_snapshot(
    *,
    trace_ids_before: set[str] | None = None,
    trace_ids: list[str] | None = None,
    challenge_id: str | None = None,
    challenge_name: str | None = None,
    run_started_at: datetime | None = None,
) -> dict[str, Any]:
    summaries = list_trace_summaries()
    if trace_ids:
        known_ids = set(trace_ids)
        relevant = [summary for summary in summaries if summary.id in known_ids]
    elif challenge_id:
        relevant = [summary for summary in summaries if summary.challenge_id == challenge_id]
        if run_started_at is not None:
            started_ts = run_started_at.timestamp()
            relevant = [
                summary
                for summary in relevant
                if _timestamp_or_zero(summary.updated_at) >= started_ts
            ]
    elif trace_ids_before is not None:
        relevant = [summary for summary in summaries if summary.id not in trace_ids_before]
    elif challenge_name:
        relevant = [summary for summary in summaries if summary.challenge_name == challenge_name]
    else:
        relevant = []

    ordered = _sort_trace_summaries_by_recency(relevant)
    latest = ordered[0] if ordered else None
    latest_flag = next((summary.flag for summary in ordered if summary.flag), None)
    mapped_status = (
        TERMINAL_TRACE_STATUS_TO_RUN_STATUS.get(latest.status) if latest is not None else None
    )

    return {
        "trace_ids": [summary.id for summary in ordered],
        "latest_trace_id": latest.id if latest else None,
        "flag": latest_flag,
        "trace_status": mapped_status,
    }


def snapshot_persisted_run(
    run: Any,
    challenge_name: str | None = None,
) -> dict[str, Any]:
    trace_ids = json.loads(run.trace_ids_json or "[]")
    trace_snapshot = _build_trace_snapshot(
        trace_ids=trace_ids,
        challenge_id=run.challenge_id,
        run_started_at=run.started_at,
        challenge_name=challenge_name if not trace_ids else None,
    )

    status = str(run.status)
    if status in ACTIVE_RUN_STATUSES and not _is_pid_running(run.pid):
        status = trace_snapshot["trace_status"] or "finished"
    elif trace_snapshot["trace_status"] and status not in {"cancelled", "gave_up"}:
        status = trace_snapshot["trace_status"]

    finished_at = run.finished_at
    if status not in ACTIVE_RUN_STATUSES and finished_at is None:
        finished_at = utcnow()

    return {
        "id": run.id,
        "challenge_id": run.challenge_id,
        "mode": run.mode,
        "status": status,
        "command": json.loads(run.command_json or "[]"),
        "workdir": run.workdir,
        "pid": run.pid if _is_pid_running(run.pid) else None,
        "output_log_path": run.output_log_path,
        "steering_log_path": run.steering_log_path,
        "flag": trace_snapshot["flag"] or run.flag,
        "latest_trace_id": trace_snapshot["latest_trace_id"] or run.latest_trace_id,
        "trace_ids": trace_snapshot["trace_ids"] or trace_ids,
        "exit_code": run.exit_code,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": finished_at,
    }
