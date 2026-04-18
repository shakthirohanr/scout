"""Model resolution — Bedrock, Azure, Fireworks, Kimi, Zen, and Google."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:
    from backend.config import Settings

# Default model fallback — overridden at runtime by DEFAULT_SOLVER_MODEL when set
FALLBACK_DEFAULT_MODEL = "openai-compatible/gpt-4o"
DEFAULT_MODELS: list[str] = [FALLBACK_DEFAULT_MODEL]

# Context window sizes (tokens)
CONTEXT_WINDOWS: dict[str, int] = {
    "us.anthropic.claude-opus-4-6-v1": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "gpt-5.4": 1_000_000,
    "gpt-5.4-mini": 400_000,
    "gpt-5.3-codex": 1_000_000,
    "gpt-5.3-codex-spark": 128_000,
    "gemini-3-flash-preview": 1_000_000,
}

# Models that support vision
VISION_MODELS: set[str] = {
    "us.anthropic.claude-opus-4-6-v1",
    "claude-opus-4-6",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gemini-3-flash-preview",
}


def resolve_model(spec: str, settings: Settings) -> Model:
    """Resolve a 'provider/model_id' spec to a Pydantic AI Model."""
    provider = provider_from_spec(spec)
    model_id = model_id_from_spec(spec)
    match provider:
        case "generic-openai" | "openai-compatible" | "openai":
            base_url = settings.openai_compatible_base_url
            api_key = settings.openai_compatible_api_key
            if not base_url:
                raise ValueError(
                    "openai_compatible_base_url not configured"
                )
            return OpenAIModel(
                model_id,
                provider=OpenAIProvider(
                    base_url=base_url,
                    api_key=api_key or "sk-dummy",
                ),
            )
        case _:
            raise ValueError(f"Unknown provider: {provider}")


def resolve_model_settings(spec: str) -> ModelSettings:
    """Get provider-specific model settings."""
    provider = provider_from_spec(spec)
    match provider:
        case "generic-openai" | "openai-compatible" | "openai":
            return OpenAIModelSettings(
                max_tokens=4096,
            )
        case _:
            return ModelSettings(max_tokens=4096)


def default_models(settings: Settings | None = None) -> list[str]:
    """Return the configured default solver model list."""
    if settings is None:
        from backend.config import Settings as RuntimeSettings

        settings = RuntimeSettings()
    configured = (settings.default_solver_model or "").strip()
    return [configured or FALLBACK_DEFAULT_MODEL]


def model_id_from_spec(spec: str) -> str:
    """Extract just the model ID from a spec, preserving embedded path segments."""
    if "/" not in spec:
        return spec
    parts = spec.split("/")
    model_parts = parts[1:]
    if effort_from_spec(spec) and model_parts:
        model_parts = model_parts[:-1]
    return "/".join(model_parts) if model_parts else spec


def provider_from_spec(spec: str) -> str:
    """Extract the provider from a spec."""
    if "/" not in spec:
        return "openai-compatible"
    return spec.split("/", 1)[0]


def effort_from_spec(spec: str) -> str | None:
    """Extract effort level from specs that support an explicit suffix."""
    provider = provider_from_spec(spec)
    if provider not in {"claude-sdk", "codex"}:
        return None
    parts = spec.split("/")
    if len(parts) >= 3 and parts[-1] in ("low", "medium", "high", "max"):
        return parts[-1]
    return None


def supports_vision(spec: str) -> bool:
    """Check if a model spec supports vision."""
    return model_id_from_spec(spec) in VISION_MODELS


def context_window(spec: str) -> int:
    """Get context window size for a model spec."""
    return CONTEXT_WINDOWS.get(model_id_from_spec(spec), 200_000)
