"""Trace listing/detail routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.utils import utcnow_iso
from backend.log_reader import get_trace_detail, list_trace_summaries, logs_directory

router = APIRouter(prefix="/api/v1", tags=["traces"])


@router.get("/traces")
def traces(challenge_id: str | None = Query(default=None)) -> dict[str, Any]:
    summaries = list_trace_summaries()
    if challenge_id is not None:
        summaries = [s for s in summaries if s.challenge_id == challenge_id]
    summaries = [summary.to_dict() for summary in summaries]
    return {
        "traces": summaries,
        "available": logs_directory().is_dir(),
        "generated_at": utcnow_iso(),
        "logs_directory": str(logs_directory()),
    }


@router.get("/traces/{trace_id}")
def trace_detail(
    trace_id: str,
    limit: int = Query(default=450, ge=1, le=5000),
) -> dict[str, Any]:
    detail = get_trace_detail(trace_id, limit=limit)
    if not detail:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return detail.to_dict()
