"""Per-run solver configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.config import CONFIG_PATH, REPO_ROOT, Settings, get_settings
from backend.models import default_models

BACKEND_DIR = REPO_ROOT / "backend"
UI_CONFIG_PATH = CONFIG_PATH

CoordinatorBackend = Literal["openai"]


class SolverRunConfig(BaseModel):
    challenges_dir: str = "challenges"
    image: str = "ctf-sandbox"
    models: list[str] = Field(default_factory=default_models)
    agent_count: int = Field(
        default=1, ge=1, le=10, description="Number of concurrent agents per challenge"
    )
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
    return SolverRunConfig()


def save_ui_config(config: SolverRunConfig) -> SolverRunConfig:
    return config


def resolve_user_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def resolve_workdir(config: SolverRunConfig) -> str:
    return str(REPO_ROOT)
