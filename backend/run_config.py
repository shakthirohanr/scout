"""Per-run solver configuration and CLI command building.

SolverRunConfig holds per-run options submitted by the web UI (challenge dir,
CTFd URL, model list, etc.).  It is distinct from Settings (infra/API config
read from agent-config.yaml).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.config import CONFIG_PATH, REPO_ROOT, Settings, get_settings, save_config
from backend.models import default_models

BACKEND_DIR = REPO_ROOT / "backend"
UI_CONFIG_PATH = CONFIG_PATH  # kept for import compat

SolverMode = Literal["ctfd", "solve", "solve-local", "solve-dir"]
CoordinatorBackend = Literal["openai"]


class SolverRunConfig(BaseModel):
    """Per-run config supplied by the web UI."""

    mode: SolverMode = "solve"
    challenge_dir: str = "."
    challenges_dir: str = "challenges"
    ctfd_url: str | None = None
    image: str = "ctf-sandbox"
    models: list[str] = Field(default_factory=default_models)
    no_submit: bool = True
    verbose: bool = False
    coordinator: CoordinatorBackend = "openai"
    coordinator_model: str | None = None
    max_challenges: int = 10
    msg_port: int = 0
    openai_compatible_base_url: str = ""
    openai_compatible_api_key: str = ""

    @field_validator("models")
    @classmethod
    def _validate_models(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item and item.strip()]
        if not normalized:
            return default_models()
        deduped: list[str] = []
        for item in normalized:
            if item not in deduped:
                deduped.append(item)
        return deduped

    @field_validator("max_challenges")
    @classmethod
    def _validate_max_challenges(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_challenges must be at least 1")
        return value

    @field_validator("msg_port")
    @classmethod
    def _validate_msg_port(cls, value: int) -> int:
        if not 0 <= value <= 65535:
            raise ValueError("msg_port must be between 0 and 65535")
        return value


def load_ui_config() -> SolverRunConfig:
    """Return defaults; the web UI always supplies its own config on start."""
    return SolverRunConfig()


def save_ui_config(config: SolverRunConfig) -> SolverRunConfig:
    # Persist OpenAI credentials from a UI-submitted run back into agent-config.yaml
    if config.openai_compatible_base_url or config.openai_compatible_api_key:
        settings = get_settings()
        if config.openai_compatible_base_url:
            settings.openai_compatible_base_url = config.openai_compatible_base_url
        if config.openai_compatible_api_key:
            settings.openai_compatible_api_key = config.openai_compatible_api_key
        save_config(settings)
    return config


def project_python_executable() -> str:
    venv_candidates = [
        REPO_ROOT / ".venv" / "bin" / "python",
        BACKEND_DIR / ".venv" / "bin" / "python",
    ]
    for venv_python in venv_candidates:
        if venv_python.exists():
            return str(venv_python)
    return sys.executable


def resolve_user_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def resolve_workdir(config: SolverRunConfig) -> str:
    if config.mode == "solve-local":
        return str(resolve_user_path(config.challenge_dir))
    return str(REPO_ROOT)


def build_cli_command(config: SolverRunConfig, ctfd_url_override: str | None = None) -> list[str]:
    """Build the subprocess command for a solver run (no CLI options — all via YAML)."""
    python_exe = project_python_executable()
    # Write per-run overrides into the config file so the subprocess picks them up
    settings = get_settings()
    if config.models:
        settings.models = config.models
    if config.no_submit is not None:
        settings.no_submit = config.no_submit
    if config.verbose is not None:
        settings.verbose = config.verbose
    if config.max_challenges:
        settings.max_concurrent_challenges = config.max_challenges
    if config.coordinator_model:
        settings.coordinator_model = config.coordinator_model
    if config.msg_port:
        settings.msg_port = config.msg_port
    if config.openai_compatible_base_url:
        settings.openai_compatible_base_url = config.openai_compatible_base_url
    if config.openai_compatible_api_key:
        settings.openai_compatible_api_key = config.openai_compatible_api_key
    save_config(settings)

    return [python_exe, "-m", "backend.cli", "run"]
