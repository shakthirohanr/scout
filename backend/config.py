"""Configuration backed by a single YAML file (backend/agent-config.yaml)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BACKEND_DIR / "agent-config.yaml"

CoordinatorBackend = Literal["openai"]


def _default_models() -> list[str]:
    return ["openai-compatible/gpt-4o"]


class Settings(BaseModel):
    # Model configuration
    models: list[str] = Field(default_factory=_default_models)
    no_submit: bool = True
    verbose: bool = False

    coordinator: CoordinatorBackend = "openai"
    coordinator_model: str | None = None
    max_challenges: int = 10
    msg_port: int = 0
    api_host: str = "127.0.0.1"
    api_port: int = 8081

    # Provider (OpenAI Compatible)
    openai_compatible_base_url: str = ""
    openai_compatible_api_key: str = ""
    default_solver_model: str = "openai-compatible/gpt-4o"

    # Database
    postgres_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/cryptoagent"
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5432/cryptoagent"

    # Infra
    sandbox_image: str = "ctf-sandbox"
    max_concurrent_challenges: int = 10
    max_attempts_per_challenge: int = 3
    container_memory_limit: str = "16g"

    def __init__(self, **data):
        if not data:
            try:
                if CONFIG_PATH.exists():
                    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
                    data = loaded
            except Exception as e:
                logger.warning("Failed to parse %s: %s. Using default settings.", CONFIG_PATH, e)
        super().__init__(**data)


def load_config() -> Settings:
    if not CONFIG_PATH.exists():
        cfg = Settings()
        save_config(cfg)
        logger.info("Created default config at %s", CONFIG_PATH)
        return cfg
    return Settings()


def save_config(config: Settings) -> Settings:
    try:
        data = config.model_dump(mode="json")
        CONFIG_PATH.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Failed to write %s: %s", CONFIG_PATH, e)
    return config


# Singleton
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = load_config()
    return _settings_instance


def reload_settings() -> Settings:
    global _settings_instance
    _settings_instance = load_config()
    return _settings_instance
