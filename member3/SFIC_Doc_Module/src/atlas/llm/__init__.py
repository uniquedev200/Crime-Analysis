"""LLM layer contracts, prompt construction, client factory, and adapters."""

from __future__ import annotations

from atlas.llm.build_prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_prompt,
    load_system_prompt,
)
from atlas.llm.client import get_llm_client
from atlas.llm.gemini_adapter import GeminiAdapter, convert_schema_for_gemini
from atlas.llm.mock import FaultyProvider, MockProvider
from atlas.llm.openai_adapter import OpenAiAdapter
from atlas.llm.retry import (
    AuthError,
    ConnectionError,
    InvalidJsonError,
    RateLimitError,
    RefusalError,
    ServerError,
    TimeoutError,
    TruncatedOutputError,
    execute_with_retry,
)

__all__ = [
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "AuthError",
    "ConnectionError",
    "FaultyProvider",
    "GeminiAdapter",
    "InvalidJsonError",
    "MockProvider",
    "OpenAiAdapter",
    "RateLimitError",
    "RefusalError",
    "ServerError",
    "TimeoutError",
    "TruncatedOutputError",
    "build_prompt",
    "convert_schema_for_gemini",
    "execute_with_retry",
    "get_llm_client",
    "load_system_prompt",
]
