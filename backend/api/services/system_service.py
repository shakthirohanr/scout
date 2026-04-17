"""System/config metadata service helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from backend.config import Settings
from backend.log_reader import logs_directory
from backend.models import CONTEXT_WINDOWS, VISION_MODELS, context_window, default_models, provider_from_spec
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
        "fireworks_api_base_url": settings.fireworks_api_base_url,
        "kimi_api_base_url": settings.kimi_api_base_url,
        "default_solver_model": settings.default_solver_model,
        "has_ctfd_token": bool(settings.ctfd_token),
        "has_anthropic_api_key": bool(settings.anthropic_api_key),
        "has_openai_api_key": bool(settings.openai_api_key),
        "has_gemini_api_key": bool(settings.gemini_api_key),
        "has_aws_bearer_token": bool(settings.aws_bearer_token),
        "has_azure_openai_api_key": bool(settings.azure_openai_api_key),
        "has_opencode_zen_api_key": bool(settings.opencode_zen_api_key),
        "has_generic_openai_api_key": bool(settings.generic_openai_api_key),
        "has_fireworks_api_key": bool(settings.fireworks_api_key),
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
    settings = Settings()
    known_specs = sorted(
        {
            *default_models(settings),
            *[f"kimi/{name}" for name in ["kimi-k2p5-turbo"]],
            *[f"azure/{name}" for name in ["gpt-5.4", "gpt-5.4-mini"]],
            *[f"codex/{name}" for name in ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"]],
            *[f"claude-sdk/{name}" for name in ["claude-opus-4-6"]],
            *[f"google/{name}" for name in ["gemini-3-flash-preview"]],
            *[
                f"fireworks/{name}"
                for name in [
                    "accounts/fireworks/models/llama-v3p1-8b-instruct",
                    "accounts/fireworks/routers/kimi-k2p5-turbo",
                ]
            ],
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


def fireworks_model_catalog(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings()
    base_url = settings.fireworks_api_base_url.rstrip("/")
    if not settings.fireworks_api_key:
        return {
            "provider": "fireworks",
            "configured": False,
            "base_url": base_url,
            "count": 0,
            "models": [],
            "error": "FIREWORKS_API_KEY is not configured",
        }

    url = f"{base_url}/models"
    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            response = client.get(
                url,
                headers={"Authorization": f"Bearer {settings.fireworks_api_key}"},
            )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        return {
            "provider": "fireworks",
            "configured": True,
            "base_url": base_url,
            "count": 0,
            "models": [],
            "error": f"Fireworks returned {exc.response.status_code}",
        }
    except Exception as exc:
        return {
            "provider": "fireworks",
            "configured": True,
            "base_url": base_url,
            "count": 0,
            "models": [],
            "error": str(exc),
        }

    models = payload.get("data", [])
    normalized = sorted(
        [
            {
                "id": str(item.get("id") or ""),
                "owned_by": str(item.get("owned_by") or ""),
                "kind": str(item.get("kind") or ""),
                "created": item.get("created"),
                "context_length": item.get("context_length"),
                "supports_chat": bool(item.get("supports_chat")),
                "supports_tools": bool(item.get("supports_tools")),
                "supports_image_input": bool(item.get("supports_image_input")),
            }
            for item in models
            if item.get("id")
        ],
        key=lambda item: item["id"],
    )
    return {
        "provider": "fireworks",
        "configured": True,
        "base_url": base_url,
        "count": len(normalized),
        "models": normalized,
    }


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
