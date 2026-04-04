"""System/config metadata service helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.config import Settings
from backend.log_reader import logs_directory
from backend.models import CONTEXT_WINDOWS, DEFAULT_MODELS, VISION_MODELS, context_window, provider_from_spec
from backend.run_config import REPO_ROOT, UI_CONFIG_PATH, load_ui_config


def settings_summary(settings: Settings) -> dict[str, Any]:
    return {
        "ctfd_url": settings.ctfd_url,
        "ctfd_user": settings.ctfd_user,
        "sandbox_image": settings.sandbox_image,
        "max_concurrent_challenges": settings.max_concurrent_challenges,
        "max_attempts_per_challenge": settings.max_attempts_per_challenge,
        "container_memory_limit": settings.container_memory_limit,
        "aws_region": settings.aws_region,
        "azure_openai_endpoint": settings.azure_openai_endpoint,
        "generic_openai_base_url": settings.generic_openai_base_url,
        "kimi_api_base_url": settings.kimi_api_base_url,
        "has_ctfd_token": bool(settings.ctfd_token),
        "has_anthropic_api_key": bool(settings.anthropic_api_key),
        "has_openai_api_key": bool(settings.openai_api_key),
        "has_gemini_api_key": bool(settings.gemini_api_key),
        "has_aws_bearer_token": bool(settings.aws_bearer_token),
        "has_azure_openai_api_key": bool(settings.azure_openai_api_key),
        "has_opencode_zen_api_key": bool(settings.opencode_zen_api_key),
        "has_generic_openai_api_key": bool(settings.generic_openai_api_key),
        "has_kimi_api_key": bool(settings.kimi_api_key),
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
    known_specs = sorted(
        {
            *DEFAULT_MODELS,
            *[f"kimi/{name}" for name in ["kimi-k2p5-turbo"]],
            *[f"azure/{name}" for name in ["gpt-5.4", "gpt-5.4-mini"]],
            *[f"codex/{name}" for name in ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"]],
            *[f"claude-sdk/{name}" for name in ["claude-opus-4-6"]],
            *[f"google/{name}" for name in ["gemini-3-flash-preview"]],
            *[f"zen/{name}" for name in ["gpt-5.3-codex-spark"]],
            *[f"bedrock/{name}" for name in CONTEXT_WINDOWS if "." in name],
        }
    )

    return [
        {
            "spec": spec,
            "provider": provider_from_spec(spec),
            "context_window": context_window(spec),
            "supports_vision": spec.split("/")[-1] in VISION_MODELS,
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
        "default_models": list(DEFAULT_MODELS),
        "supported_modes": ["ctfd", "solve", "solve-local", "solve-dir"],
        "supported_coordinators": ["kimi", "claude", "codex"],
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
