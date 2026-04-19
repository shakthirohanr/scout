from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.sse import EventSourceResponse

from backend.api.state import ORCHESTRATOR
from backend.api.utils import utcnow_iso
from backend.log_reader import _parse_event_line, _safe_trace_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["events"])

RUN_POLL_INTERVAL = 2.0
TRACE_POLL_INTERVAL = 1.5


def _run_snapshot(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "challenge_id": run.challenge_id,
        "status": run.status,
        "timestamp": utcnow_iso(),
    }


async def _runs_event_stream(request: Request) -> Any:
    prev_statuses: dict[str, str] = {}

    active_runs = ORCHESTRATOR.agent_runner.list_runs()
    for run in active_runs:
        prev_statuses[run.run_id] = run.status

    snapshot = [_run_snapshot(run) for run in active_runs]
    yield {
        "event": "connected",
        "data": json.dumps({"runs": snapshot, "timestamp": utcnow_iso()}),
    }

    while True:
        if await request.is_disconnected():
            break

        await asyncio.sleep(RUN_POLL_INTERVAL)

        if await request.is_disconnected():
            break

        current_runs = ORCHESTRATOR.agent_runner.list_runs()
        current_ids = {run.run_id for run in current_runs}

        for run in current_runs:
            prev_status = prev_statuses.get(run.run_id)
            if prev_status is None:
                yield {
                    "event": "run_started",
                    "data": json.dumps(_run_snapshot(run)),
                }
            elif prev_status != run.status:
                event_type = (
                    "run_finished"
                    if run.status in {"solved", "finished", "failed", "cancelled", "gave_up"}
                    else "run_status_changed"
                )
                yield {
                    "event": event_type,
                    "data": json.dumps(_run_snapshot(run)),
                }

        finished_ids = set(prev_statuses.keys()) - current_ids
        for run_id in finished_ids:
            yield {
                "event": "run_finished",
                "data": json.dumps(
                    {
                        "run_id": run_id,
                        "status": prev_statuses[run_id],
                        "timestamp": utcnow_iso(),
                    }
                ),
            }

        prev_statuses = {run.run_id: run.status for run in current_runs}


@router.get("/events/runs")
async def sse_runs(request: Request) -> EventSourceResponse:
    return EventSourceResponse(_runs_event_stream(request))


async def _trace_event_stream(trace_id: str, request: Request) -> Any:
    path = _safe_trace_path(trace_id)
    if not path or not path.exists():
        yield {
            "event": "error",
            "data": json.dumps({"error": "Trace not found", "trace_id": trace_id}),
        }
        return

    last_line_count = 0
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        last_line_count = len(lines)
    except Exception:
        pass

    yield {
        "event": "connected",
        "data": json.dumps(
            {
                "trace_id": trace_id,
                "line_count": last_line_count,
                "timestamp": utcnow_iso(),
            }
        ),
    }

    while True:
        if await request.is_disconnected():
            break

        await asyncio.sleep(TRACE_POLL_INTERVAL)

        if await request.is_disconnected():
            break

        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.readlines()
            current_count = len(lines)
        except Exception:
            continue

        if current_count > last_line_count:
            for line in lines[last_line_count:]:
                stripped = line.strip()
                if not stripped:
                    continue
                event = _parse_event_line(stripped)
                if event:
                    yield {
                        "event": "trace_event",
                        "data": json.dumps({"trace_id": trace_id, "event": event}),
                    }
            last_line_count = current_count


@router.get("/events/traces/{trace_id}")
async def sse_trace(trace_id: str, request: Request) -> EventSourceResponse:
    return EventSourceResponse(_trace_event_stream(trace_id, request))
