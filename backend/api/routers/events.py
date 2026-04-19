from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.sse import ServerSentEvent, format_sse_event
from starlette.responses import StreamingResponse

from backend.api.state import ORCHESTRATOR
from backend.api.utils import utcnow_iso
from backend.log_reader import _parse_event_line, _safe_trace_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["events"])

RUN_POLL_INTERVAL = 2.0
TRACE_POLL_INTERVAL = 1.5
KEEPALIVE_INTERVAL = 12.0


def _run_snapshot(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "challenge_id": run.challenge_id,
        "status": run.status,
        "timestamp": utcnow_iso(),
    }


async def _runs_event_stream(request: Request) -> Any:
    prev_statuses: dict[str, str] = {}

    try:
        active_runs = ORCHESTRATOR.agent_runner.list_runs()
    except Exception:
        active_runs = []

    for run in active_runs:
        prev_statuses[run.run_id] = run.status

    yield format_sse_event(
        event="connected",
        data_str=json.dumps(
            {"runs": [_run_snapshot(r) for r in active_runs], "timestamp": utcnow_iso()}
        ),
    )

    last_keepalive = asyncio.get_event_loop().time()

    try:
        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(RUN_POLL_INTERVAL)

            if await request.is_disconnected():
                break

            now = asyncio.get_event_loop().time()
            if now - last_keepalive >= KEEPALIVE_INTERVAL:
                yield format_sse_event(comment="keepalive")
                last_keepalive = now

            try:
                current_runs = ORCHESTRATOR.agent_runner.list_runs()
            except Exception:
                continue

            current_ids = {run.run_id for run in current_runs}

            for run in current_runs:
                prev_status = prev_statuses.get(run.run_id)
                if prev_status is None:
                    yield format_sse_event(
                        event="run_started",
                        data_str=json.dumps(_run_snapshot(run)),
                    )
                elif prev_status != run.status:
                    event_type = (
                        "run_finished"
                        if run.status in {"solved", "finished", "failed", "cancelled", "gave_up"}
                        else "run_status_changed"
                    )
                    yield format_sse_event(
                        event=event_type,
                        data_str=json.dumps(_run_snapshot(run)),
                    )

            finished_ids = set(prev_statuses.keys()) - current_ids
            for run_id in finished_ids:
                yield format_sse_event(
                    event="run_finished",
                    data_str=json.dumps(
                        {
                            "run_id": run_id,
                            "status": prev_statuses[run_id],
                            "timestamp": utcnow_iso(),
                        }
                    ),
                )

            prev_statuses = {run.run_id: run.status for run in current_runs}
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("SSE runs stream error")


@router.get("/events/runs")
async def sse_runs(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _runs_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _trace_event_stream(trace_id: str, request: Request) -> Any:
    path = _safe_trace_path(trace_id)
    if not path or not path.exists():
        yield format_sse_event(
            event="error",
            data_str=json.dumps({"error": "Trace not found", "trace_id": trace_id}),
        )
        return

    last_line_count = 0
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        last_line_count = len(lines)
    except Exception:
        pass

    yield format_sse_event(
        event="connected",
        data_str=json.dumps(
            {
                "trace_id": trace_id,
                "line_count": last_line_count,
                "timestamp": utcnow_iso(),
            }
        ),
    )

    last_keepalive = asyncio.get_event_loop().time()

    try:
        while True:
            if await request.is_disconnected():
                break

            await asyncio.sleep(TRACE_POLL_INTERVAL)

            if await request.is_disconnected():
                break

            now = asyncio.get_event_loop().time()
            if now - last_keepalive >= KEEPALIVE_INTERVAL:
                yield format_sse_event(comment="keepalive")
                last_keepalive = now

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
                        yield format_sse_event(
                            event="trace_event",
                            data_str=json.dumps({"trace_id": trace_id, "event": event}),
                        )
                last_line_count = current_count
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("SSE trace stream error")


@router.get("/events/traces/{trace_id}")
async def sse_trace(trace_id: str, request: Request) -> StreamingResponse:
    return StreamingResponse(
        _trace_event_stream(trace_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
