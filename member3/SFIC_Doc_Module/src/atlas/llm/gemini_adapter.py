"""Google GenAI structured output adapter implementing LlmClientPort.

Uses `google-genai` SDK 2.30.0 with `GenerateContentConfig(response_mime_type='application/json')`,
OpenAPI 3.0 schema conversion, temperature=0, response validation, secret-safe error mapping,
and retry policies.
"""

from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from atlas.contracts.model_schema import MODEL_SCHEMA, validate_model_output
from atlas.errors import ProviderError, SchemaViolationError
from atlas.llm.pacing import RateLimiter
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
from atlas.ports.llm import LlmClientPort


def convert_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert JSON schema draft-7 types into Gemini OpenAPI 3.0 format.

    In particular, converts ['string', 'null'] type lists into `type='string'`
    with `nullable=True`, and removes null/None from enum lists while setting nullable=True.
    """
    if not isinstance(schema, dict):
        return schema

    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, list):
            non_null = [t for t in value if t != "null"]
            t_val = non_null[0] if non_null else "string"
            result["type"] = t_val
            if "null" in value:
                result["nullable"] = True
        elif isinstance(value, dict):
            result[key] = convert_schema_for_gemini(value)
        elif isinstance(value, list):
            result[key] = [convert_schema_for_gemini(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value

    if "enum" in result and isinstance(result["enum"], list) and None in result["enum"]:
        result["enum"] = [e for e in result["enum"] if e is not None]
        result["nullable"] = True

    return result


class GeminiAdapter(LlmClientPort):
    """Adapter for Google Gemini models using google-genai 2.30.0 SDK."""

    # This adapter owns its retry loop, so callers must not wrap it again.
    handles_retries = True

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        temperature: float = 0.0,
        timeout_s: float = 60.0,
        max_attempts: int = 3,
        client: genai.Client | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be non-empty")
        self._model_name = model_name
        self._temperature = temperature
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._rate_limiter = rate_limiter
        self._client = client or genai.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _call_raw(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform single API call and return validated dictionary or raise categorized errors."""
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        effective_schema = schema if schema else MODEL_SCHEMA
        gemini_schema = convert_schema_for_gemini(effective_schema)

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=gemini_schema,
            temperature=self._temperature,
        )

        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=user,
                config=config,
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code in (401, 403):
                raise AuthError("Authentication/authorization failed for Gemini API (401/403).") from None
            if code == 429:
                raise RateLimitError("Gemini rate limit exceeded (429)") from None
            if code is not None and 500 <= code < 600:
                raise ServerError(f"Gemini server error ({code})") from None
            if isinstance(exc, genai_errors.ServerError):
                raise ServerError("Gemini server error (5xx)") from None
            raise ProviderError(f"Gemini API error with status {code}") from None
        except Exception as exc:
            exc_name = type(exc).__name__.lower()
            if "timeout" in exc_name:
                raise TimeoutError("Gemini request timed out") from None
            if "connect" in exc_name:
                raise ConnectionError("Gemini connection error") from None
            raise ProviderError(f"Gemini error: {type(exc).__name__}") from None

        candidates = getattr(response, "candidates", None)
        if candidates:
            first_cand = candidates[0]
            finish_reason = getattr(first_cand, "finish_reason", None)
            finish_str = str(finish_reason).upper()
            if "MAX_TOKENS" in finish_str:
                raise TruncatedOutputError("Gemini output truncated (MAX_TOKENS finish)")
            if any(k in finish_str for k in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY")):
                raise RefusalError(f"Gemini response blocked by safety filter: {finish_reason}")

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise InvalidJsonError("Gemini returned empty response text")

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(f"Failed to parse Gemini response as JSON: {exc}") from exc

        try:
            return validate_model_output(parsed)
        except ValueError as exc:
            raise SchemaViolationError(f"Gemini response violated schema: {exc}") from exc

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform schema-constrained extraction with Section 5.9 retries."""
        return execute_with_retry(
            lambda: self._call_raw(system, user, schema),
            max_attempts=self._max_attempts,
        )


__all__ = [
    "GeminiAdapter",
    "convert_schema_for_gemini",
]
