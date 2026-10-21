"""LLM client factory returning active provider adapter implementing LlmClientPort."""

from __future__ import annotations

from atlas.config import AtlasSettings, get_settings
from atlas.errors import ConfigError
from atlas.llm.gemini_adapter import GeminiAdapter
from atlas.llm.mock import FaultyProvider, MockProvider
from atlas.llm.openai_adapter import OpenAiAdapter
from atlas.llm.pacing import RateLimiter
from atlas.ports.llm import LlmClientPort


def _build_rate_limiter(cfg: AtlasSettings) -> RateLimiter:
    """Build a client-side rate limiter from configuration (no hardcoded limits)."""
    return RateLimiter.from_settings(
        max_requests_per_minute=cfg.LLM_MAX_REQUESTS_PER_MINUTE,
        min_interval_s=cfg.LLM_MIN_INTERVAL_S,
        window_s=cfg.LLM_RATE_WINDOW_S,
    )


def _require_model(cfg: AtlasSettings, provider: str) -> str:
    """Return the configured model id for a live provider.

    Model names are never hardcoded or defaulted from memory (AGENTS.md rule 9):
    the operator selects the model with ``LLM_MODEL`` and the verified choice is
    recorded in ``docs/DECISIONS.md``.
    """
    model = cfg.LLM_MODEL.strip() if cfg.LLM_MODEL else ""
    if not model:
        raise ConfigError(
            f"Missing required configuration: LLM_MODEL must name the model to use when LLM_PROVIDER is '{provider}'."
        )
    return model


def get_llm_client(settings: AtlasSettings | None = None) -> LlmClientPort:
    """Return configured LLM client adapter implementing LlmClientPort.

    Args:
        settings: Optional AtlasSettings instance. If omitted, loaded from environment.

    Returns:
        LlmClientPort implementation (MockProvider, FaultyProvider, OpenAiAdapter, or GeminiAdapter).

    Raises:
        ConfigError: If provider credentials are missing or provider name is unrecognized.
            Error messages are guaranteed secret-safe.
    """
    cfg = settings or get_settings()
    provider = cfg.LLM_PROVIDER.lower().strip()

    if provider == "mock":
        return MockProvider()

    if provider == "faulty":
        return FaultyProvider()

    if provider == "openai":
        if not cfg.OPENAI_API_KEY or not cfg.OPENAI_API_KEY.get_secret_value().strip():
            raise ConfigError(
                "Missing required configuration: OPENAI_API_KEY must be configured when LLM_PROVIDER is 'openai'."
            )
        model = _require_model(cfg, "openai")
        return OpenAiAdapter(
            api_key=cfg.OPENAI_API_KEY.get_secret_value(),
            model_name=model,
            temperature=cfg.LLM_TEMPERATURE,
            timeout_s=cfg.LLM_TIMEOUT_S,
            max_attempts=cfg.LLM_MAX_ATTEMPTS,
            rate_limiter=_build_rate_limiter(cfg),
        )

    if provider == "gemini":
        if not cfg.GEMINI_API_KEY or not cfg.GEMINI_API_KEY.get_secret_value().strip():
            raise ConfigError(
                "Missing required configuration: GEMINI_API_KEY must be configured when LLM_PROVIDER is 'gemini'."
            )
        model = _require_model(cfg, "gemini")
        return GeminiAdapter(
            api_key=cfg.GEMINI_API_KEY.get_secret_value(),
            model_name=model,
            temperature=cfg.LLM_TEMPERATURE,
            timeout_s=cfg.LLM_TIMEOUT_S,
            max_attempts=cfg.LLM_MAX_ATTEMPTS,
            rate_limiter=_build_rate_limiter(cfg),
        )

    if provider == "groq":
        key = (
            cfg.GROQ_API_KEY.get_secret_value()
            if cfg.GROQ_API_KEY
            else (cfg.OPENAI_API_KEY.get_secret_value() if cfg.OPENAI_API_KEY else "")
        )
        if not key.strip():
            raise ConfigError(
                "Missing required configuration: GROQ_API_KEY must be configured when LLM_PROVIDER is 'groq'."
            )
        model = _require_model(cfg, "groq")
        base_url = cfg.OPENAI_BASE_URL.strip() if cfg.OPENAI_BASE_URL else "https://api.groq.com/openai/v1"
        return OpenAiAdapter(
            api_key=key,
            model_name=model,
            base_url=base_url,
            provider_override="groq",
            temperature=cfg.LLM_TEMPERATURE,
            timeout_s=cfg.LLM_TIMEOUT_S,
            max_attempts=cfg.LLM_MAX_ATTEMPTS,
            rate_limiter=_build_rate_limiter(cfg),
        )

    raise ConfigError(f"Unsupported LLM_PROVIDER: {cfg.LLM_PROVIDER}")


__all__ = ["get_llm_client"]
