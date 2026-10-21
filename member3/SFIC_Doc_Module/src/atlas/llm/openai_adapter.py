"""OpenAI structured output adapter implementing LlmClientPort.

Uses OpenAI SDK 3.29.0 structured outputs (`response_format={'type': 'json_schema', ...}`)
with temperature=0, response validation, secret-safe error mapping, and retry policies.
"""

from __future__ import annotations

import json
from typing import Any

import openai
from openai import OpenAI

from atlas.contracts.model_schema import MODEL_SCHEMA, validate_model_output
from atlas.errors import ProviderError, SchemaViolationError
from atlas.llm.pacing import RateLimiter, parse_retry_after
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


class OpenAiAdapter(LlmClientPort):
    """Adapter for OpenAI models with strict schema structured outputs."""

    # This adapter owns its retry loop, so callers must not wrap it again.
    handles_retries = True

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        timeout_s: float = 60.0,
        max_attempts: int = 3,
        client: OpenAI | None = None,
        base_url: str | None = None,
        provider_override: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must be non-empty")
        self._model_name = model_name
        self._temperature = temperature
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._provider_name = provider_override or "openai"
        self._rate_limiter = rate_limiter
        if client is not None:
            self._client = client
        elif base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        else:
            self._client = OpenAI(api_key=api_key, timeout=timeout_s)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def _call_raw(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform single API call and return validated dictionary or raise categorized errors."""
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        effective_schema = schema if schema else MODEL_SCHEMA
        try:
            response = self._client.chat.completions.create(
                model=self._model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "model_output",
                        "strict": True,
                        "schema": effective_schema,
                    },
                },
                temperature=self._temperature,
            )
        except openai.AuthenticationError:
            raise AuthError("Authentication failed for OpenAI API (401). Check credentials.") from None
        except openai.PermissionDeniedError:
            raise AuthError("Permission denied for OpenAI API (403). Check credentials.") from None
        except openai.RateLimitError as exc:
            retry_after: float | None = None
            if hasattr(exc, "response") and exc.response is not None and hasattr(exc.response, "headers"):
                headers = exc.response.headers
                for header_name in (
                    "retry-after",
                    "x-ratelimit-reset-requests",
                    "x-ratelimit-reset-tokens",
                ):
                    retry_after = parse_retry_after(headers.get(header_name))
                    if retry_after is not None:
                        break
            if self._rate_limiter is not None:
                self._rate_limiter.notify_retry_after(retry_after)
            raise RateLimitError("OpenAI rate limit exceeded (429)", retry_after=retry_after) from None
        except openai.InternalServerError:
            raise ServerError("OpenAI server error (500)") from None
        except openai.APITimeoutError:
            raise TimeoutError("OpenAI request timed out") from None
        except openai.APIConnectionError:
            raise ConnectionError("OpenAI network connection failed") from None
        except openai.LengthFinishReasonError:
            raise TruncatedOutputError("OpenAI output truncated (length finish)") from None
        except openai.ContentFilterFinishReasonError:
            raise RefusalError("OpenAI request blocked by safety filter") from None
        except openai.APIStatusError as exc:
            code = getattr(exc, "status_code", None)
            if code in (401, 403):
                raise AuthError("Authentication/authorization failed for OpenAI API (401/403).") from None
            if code == 429:
                raise RateLimitError("OpenAI rate limit exceeded (429)") from None
            if code is not None and 500 <= code < 600:
                raise ServerError(f"OpenAI server error ({code})") from None
            raise ProviderError(f"OpenAI API error with status {code}") from None
        except openai.OpenAIError as exc:
            raise ProviderError(f"OpenAI client error: {type(exc).__name__}") from None

        if not response.choices:
            raise ProviderError("OpenAI returned no choices in response")

        choice = response.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason == "length":
            raise TruncatedOutputError("OpenAI output truncated (length finish)")
        if finish_reason == "content_filter":
            raise RefusalError("OpenAI content filter blocked response")

        message = choice.message
        if getattr(message, "refusal", None):
            raise RefusalError("OpenAI refused to generate response")

        content = message.content
        if not content:
            raise InvalidJsonError("OpenAI returned empty message content")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(f"Failed to parse OpenAI response as JSON: {exc}") from exc

        try:
            return validate_model_output(parsed)
        except ValueError as exc:
            raise SchemaViolationError(f"OpenAI response violated schema: {exc}") from exc

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform schema-constrained extraction with Section 5.9 retries."""
        return execute_with_retry(
            lambda: self._call_raw(system, user, schema),
            max_attempts=self._max_attempts,
        )


__all__ = ["OpenAiAdapter"]
