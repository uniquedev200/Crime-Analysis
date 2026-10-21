"""Retry logic and error classification adhering to PLAN.md Section 5.9.

Retry Matrix:
- 429, 5xx, timeout, connection error:
  Retry up to LLM_MAX_ATTEMPTS (default 3) total, base 2s exponential backoff
  with jitter, honor Retry-After header.
- Output truncated (length finish):
  Split chunk in half once and re-run (or raise TruncatedOutputError signal).
- Non-JSON or schema-invalid:
  1 retry of that chunk, then chunk failed_validation (SchemaViolationError).
- Refusal/safety block:
  No retry; chunk chunk_failed (RefusalError).
- 401/403:
  No retry; fail fast with secret-safe message (never print API key or secret).
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

from atlas.errors import ProviderError, RetryExhaustedError, SchemaViolationError
from atlas.ports.llm import LlmClientPort


class RateLimitError(ProviderError):
    """Raised when provider returns HTTP 429 rate limit."""

    def __init__(self, message: str = "Rate limit exceeded (429)", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ServerError(ProviderError):
    """Raised when provider returns HTTP 5xx server error."""


class TimeoutError(ProviderError):
    """Raised when LLM request times out."""


class ConnectionError(ProviderError):
    """Raised when network connection to provider fails."""


class TruncatedOutputError(ProviderError):
    """Raised when LLM generation finished due to length/token limit."""


class InvalidJsonError(ProviderError):
    """Raised when LLM output cannot be parsed as JSON."""


class RefusalError(ProviderError):
    """Raised when LLM refuses the request due to safety or policy block."""


class AuthError(ProviderError):
    """Raised on 401/403 unauthorized or forbidden errors without leaking secrets."""


def execute_with_retry(
    target: Callable[[], dict[str, Any]] | LlmClientPort,
    system: str | None = None,
    user: str | None = None,
    schema: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    base_backoff_s: float = 2.0,
    jitter: bool = True,
    sleep_fn: Callable[[float], None] = time.sleep,
    split_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute LLM extraction call adhering strictly to the Section 5.9 retry matrix.

    Args:
        target: A parameterless callable returning dict, or an LlmClientPort instance.
        system: System prompt (used if target is an LlmClientPort).
        user: User prompt (used if target is an LlmClientPort).
        schema: Model schema (used if target is an LlmClientPort).
        max_attempts: Maximum attempts for transient errors (429, 5xx, timeout, connection).
        base_backoff_s: Base backoff in seconds for exponential backoff.
        jitter: Whether to add random jitter to exponential backoff.
        sleep_fn: Sleep function (injectable for instant unit testing).
        split_fn: Optional callback to split chunk and re-run on TruncatedOutputError.

    Returns:
        Validated extraction output dictionary.

    Raises:
        AuthError: Immediate failure on 401/403 (0 retries).
        RefusalError: Immediate failure on safety refusal (0 retries).
        SchemaViolationError: Raised if schema violation persists after 1 retry.
        TruncatedOutputError: If output is truncated and no split_fn provided.
        RetryExhaustedError: If transient errors exceed max_attempts.
    """
    call_fn: Callable[[], dict[str, Any]]
    if hasattr(target, "extract"):
        client = target
        # Single retry layer: adapters that own their retry loop (and pacing) must
        # not be wrapped again, otherwise a 429 from an inner 3-attempt loop would be
        # retried 3 more times by the outer loop (a 9-request burst).
        if getattr(client, "handles_retries", False):
            return client.extract(system or "", user or "", schema or {})

        sys_prompt = system or ""
        usr_prompt = user or ""
        sch = schema or {}

        def call_fn() -> dict[str, Any]:
            return client.extract(sys_prompt, usr_prompt, sch)
    else:
        call_fn = target

    attempt = 0
    transient_attempt = 0
    schema_retry_done = False

    while True:
        attempt += 1
        try:
            return call_fn()
        except (AuthError, RefusalError, RetryExhaustedError):
            # 401/403, refusal, or already-exhausted retries: fail fast without retrying
            raise
        except TruncatedOutputError as exc:
            # Output truncated (length finish): split chunk in half once and re-run
            if split_fn is not None:
                return split_fn()
            raise exc
        except (InvalidJsonError, SchemaViolationError, ValueError) as exc:
            # Non-JSON or schema-invalid: 1 retry of that chunk, then chunk failed_validation
            if not schema_retry_done:
                schema_retry_done = True
                continue
            if isinstance(exc, SchemaViolationError):
                raise
            raise SchemaViolationError(f"Schema validation failed after retry: {exc}") from exc
        except (RateLimitError, ServerError, TimeoutError, ConnectionError) as exc:
            # 429, 5xx, timeout, connection error: up to LLM_MAX_ATTEMPTS total
            transient_attempt += 1
            if transient_attempt >= max_attempts:
                raise RetryExhaustedError(
                    f"LLM request retries exhausted after {transient_attempt} attempts: {exc}"
                ) from exc

            # Calculate backoff duration
            if isinstance(exc, RateLimitError) and exc.retry_after is not None:
                wait_s = max(0.0, float(exc.retry_after))
            else:
                wait_s = base_backoff_s * (2 ** (transient_attempt - 1))
                if jitter:
                    wait_s += random.uniform(0.0, 1.0)

            sleep_fn(wait_s)
        except Exception as exc:
            # Unclassified provider or runtime errors
            transient_attempt += 1
            if transient_attempt >= max_attempts:
                raise RetryExhaustedError(
                    f"LLM request retries exhausted after {transient_attempt} attempts: {exc}"
                ) from exc
            wait_s = base_backoff_s * (2 ** (transient_attempt - 1))
            if jitter:
                wait_s += random.uniform(0.0, 1.0)
            sleep_fn(wait_s)


__all__ = [
    "AuthError",
    "ConnectionError",
    "InvalidJsonError",
    "RateLimitError",
    "RefusalError",
    "ServerError",
    "TimeoutError",
    "TruncatedOutputError",
    "execute_with_retry",
]
