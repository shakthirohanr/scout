"""Solver run routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import RunOutputResponse, StartRunRequest
from backend.api.state import RUN_MANAGER
from backend.config import Settings
from backend.run_config import load_ui_config, save_ui_config


router = APIRouter(prefix="/api/v1", tags=["runs"])


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/runs")
def runs() -> dict[str, Any]:
    return {
        "runs": RUN_MANAGER.list_runs(),
        "generated_at": _utcnow_iso(),
    }


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    try:
        return RUN_MANAGER.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@router.post("/runs")
def start_run(request: StartRunRequest) -> dict[str, Any]:
    settings = Settings()
    config = request.config or load_ui_config()
    if request.persist_config:
        save_ui_config(config)

    try:
        return RUN_MANAGER.start(config, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, Any]:
    try:
        return RUN_MANAGER.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


@router.get("/runs/{run_id}/output", response_model=RunOutputResponse)
def run_output(
    run_id: str,
    lines: int = Query(default=200, ge=1, le=5000),
) -> RunOutputResponse:
    try:
        payload = RUN_MANAGER.tail_output(run_id, lines=lines)
        return RunOutputResponse.model_validate(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
