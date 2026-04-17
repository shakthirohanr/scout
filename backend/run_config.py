"""Persistent UI-facing run configuration and CLI command building."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.models import default_models

REPO_ROOT = Path(__file__).resolve().parent.parent
UI_CONFIG_PATH = REPO_ROOT / ".ctf-agent-ui.json"

SolverMode = Literal["ctfd", "solve", "solve-local", "solve-dir"]
CoordinatorBackend = Literal["kimi", "claude", "codex"]


class SolverRunConfig(BaseModel):
    mode: SolverMode = "solve"
    challenge_dir: str = "./challenges/excellent-crypto-challenge"
    challenges_dir: str = "challenges"
    ctfd_url: str | None = None
    image: str = "ctf-sandbox"
    models: list[str] = Field(default_factory=default_models)
    no_submit: bool = True
    verbose: bool = False
    coordinator: CoordinatorBackend = "kimi"
    coordinator_model: str | None = None
    max_challenges: int = 10
    msg_port: int = 0

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
    if not UI_CONFIG_PATH.exists():
        return SolverRunConfig()
    try:
        return SolverRunConfig.model_validate(json.loads(UI_CONFIG_PATH.read_text(encoding="utf-8")))
    except Exception:
        return SolverRunConfig()


def save_ui_config(config: SolverRunConfig) -> SolverRunConfig:
    UI_CONFIG_PATH.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return config


def project_python_executable() -> str:
    venv_candidates = [
        REPO_ROOT / "backend" / ".venv" / "bin" / "python",
        REPO_ROOT / ".venv" / "bin" / "python",
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
    python_exe = project_python_executable()
    cmd = [python_exe, "-m", "backend.cli"]

    if config.mode == "ctfd":
        cmd += [
            "run",
            "--challenges-dir",
            config.challenges_dir,
            "--coordinator",
            config.coordinator,
            "--max-challenges",
            str(config.max_challenges),
            "--msg-port",
            str(config.msg_port),
        ]
        ctfd_url = ctfd_url_override or config.ctfd_url
        if ctfd_url:
            cmd += ["--ctfd-url", ctfd_url]
        if config.coordinator_model:
            cmd += ["--coordinator-model", config.coordinator_model]
    elif config.mode == "solve":
        cmd += ["solve", config.challenge_dir]
    elif config.mode == "solve-local":
        cmd += ["solve-local"]
    elif config.mode == "solve-dir":
        cmd += ["solve-dir", config.challenges_dir]
    else:
        raise ValueError(f"Unknown mode: {config.mode}")

    if config.image:
        cmd += ["--image", config.image]
    for model in config.models:
        cmd += ["--models", model]
    if config.no_submit:
        cmd.append("--no-submit")
    if config.verbose:
        cmd.append("-v")
    return cmd
