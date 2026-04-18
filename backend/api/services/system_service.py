"""System/config metadata service helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from backend.config import Settings
from backend.log_reader import logs_directory
from backend.models import (
    context_window,
    default_models,
    provider_from_spec,
)
from backend.run_config import REPO_ROOT, UI_CONFIG_PATH, load_ui_config


def settings_summary(settings: Settings) -> dict[str, Any]:
    return {
        "sandbox_image": settings.sandbox_image,
        "max_concurrent_challenges": settings.max_concurrent_challenges,
        "max_attempts_per_challenge": settings.max_attempts_per_challenge,
        "container_memory_limit": settings.container_memory_limit,
        "openai_compatible_base_url": settings.openai_compatible_base_url,
        "default_solver_model": settings.default_solver_model,
        "has_openai_compatible_api_key": bool(settings.openai_compatible_api_key),
    }


def project_version() -> str:
    try:
        import tomllib

        candidates = [REPO_ROOT / "backend" / "pyproject.toml", REPO_ROOT / "pyproject.toml"]
        for path in candidates:
            if path.exists():
                data = tomllib.loads(path.read_text(encoding="utf-8"))
                return str(data.get("project", {}).get("version", "unknown"))
        return "unknown"
    except Exception:
        return "unknown"


def model_catalog() -> list[dict[str, Any]]:
    settings = Settings()
    known_specs = sorted(
        {
            *default_models(settings),
            *[f"openai-compatible/{name}" for name in ["gpt-4o", "gpt-4o-mini"]],
        }
    )

    return [
        {
            "spec": spec,
            "provider": provider_from_spec(spec),
            "context_window": context_window(spec),
            "supports_vision": True,
        }
        for spec in known_specs
    ]





def info_payload(active_runs: list[dict[str, Any]]) -> dict[str, Any]:
    settings = Settings()
    saved_config = load_ui_config()
    return {
        "api_version": project_version(),
        "repository_root": str(REPO_ROOT),
        "logs_directory": str(logs_directory()),
        "config_path": str(UI_CONFIG_PATH),
        "python_executable": os.sys.executable,
        "default_models": default_models(settings),
        "supported_modes": ["ctfd", "solve", "solve-local", "solve-dir"],
        "supported_coordinators": ["openai"],
        "saved_run_config": saved_config.model_dump(mode="json"),
        "settings_summary": settings_summary(settings),
        "model_catalog": model_catalog(),
        "active_runs": [run for run in active_runs if run.get("status") == "running"],
    }


def config_payload() -> dict[str, Any]:
    settings = Settings()
    return {
        "run_config": load_ui_config(),
        "config_path": str(UI_CONFIG_PATH),
        "settings_summary": settings_summary(settings),
    }


def logs_dir_exists() -> bool:
    return Path(logs_directory()).is_dir()
