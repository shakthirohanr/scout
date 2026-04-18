"""System and configuration API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.schemas import ConfigResponse
from backend.api.services.system_service import info_payload, settings_summary
from backend.api.state import ORCHESTRATOR
from backend.config import Settings
from backend.run_config import SolverRunConfig, save_ui_config

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/info")
def info() -> dict[str, Any]:
    return info_payload(ORCHESTRATOR.list_runs())


@router.get("/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    settings = Settings()
    from backend.run_config import UI_CONFIG_PATH, load_ui_config

    return ConfigResponse(
        run_config=load_ui_config(),
        config_path=str(UI_CONFIG_PATH),
        settings_summary=settings_summary(settings),
    )


@router.put("/config", response_model=ConfigResponse)
def put_config(config: SolverRunConfig) -> ConfigResponse:
    saved = save_ui_config(config)
    settings = Settings()
    from backend.run_config import UI_CONFIG_PATH

    return ConfigResponse(
        run_config=saved,
        config_path=str(UI_CONFIG_PATH),
        settings_summary=settings_summary(settings),
    )
