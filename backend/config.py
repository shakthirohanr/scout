"""Pydantic Settings — credentials from .env file + environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    postgres_url: str = ""
    database_url: str = ""

    # CTFd
    ctfd_url: str | None = None
    ctfd_user: str = "admin"
    ctfd_pass: str = "admin"
    ctfd_token: str = ""

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # Provider-specific (optional, for Bedrock/Azure/Zen fallback)
    aws_region: str = "us-east-1"
    aws_bearer_token: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    opencode_zen_api_key: str = ""
    generic_openai_base_url: str = ""
    generic_openai_api_key: str = ""
    fireworks_api_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_api_key: str = ""
    kimi_api_base_url: str = "https://llm.proxies.of.achyuth.dev/v1"
    kimi_api_key: str = "sk-3szEtbSmXUqO1lWI1cOCsA"
    default_solver_model: str = "kimi/kimi-k2p5-turbo"

    # Infra
    sandbox_image: str = "ctf-sandbox"
    max_concurrent_challenges: int = 10
    max_attempts_per_challenge: int = 3
    container_memory_limit: str = "16g"

    model_config = {
        "env_file": ("backend/.env", ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
