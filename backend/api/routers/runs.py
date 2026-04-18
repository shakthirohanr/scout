"""Solver run routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import RunOutputResponse
from backend.api.state import ORCHESTRATOR
from backend.api.utils import utcnow_iso

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.get("/runs")
def runs() -> dict[str, Any]:
    return {
        "runs": ORCHESTRATOR.list_runs(),
        "generated_at": utcnow_iso(),
    }


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    try:
        return ORCHESTRATOR.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    try:
        return await ORCHESTRATOR.kill(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@router.get("/runs/{run_id}/output", response_model=RunOutputResponse)
def run_output(
    run_id: str,
    lines: int = Query(default=200, ge=1, le=5000),
) -> RunOutputResponse:
    import collections
    from pathlib import Path

    snapshot = ORCHESTRATOR.get_run(run_id)
    log_path = snapshot.get("output_log_path", "")

    path = Path(log_path)
    if not path.exists():
        content = ""
    else:
        with open(path, encoding="utf-8") as handle:
            content = "".join(collections.deque(handle, maxlen=max(lines, 1)))

    return RunOutputResponse(
        run_id=run_id,
        log_path=log_path,
        content=content,
    )
