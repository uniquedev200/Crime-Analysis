"""Gate 2 unit tests for LLM retry matrix adhering to PLAN.md Section 5.9."""

from __future__ import annotations

import pytest

from atlas.contracts.model_schema import MODEL_SCHEMA
from atlas.errors import RetryExhaustedError, SchemaViolationError
from atlas.llm.mock import FaultyProvider
from atlas.llm.retry import (
    AuthError,
    RefusalError,
    TruncatedOutputError,
    execute_with_retry,
)


@pytest.mark.gate2
def test_retry_matrix_429_backoff_and_recovery() -> None:
    """Row 1: 429 rate limit retries up to max_attempts with exponential backoff."""
    recorded_sleeps: list[float] = []

    def mock_sleep(s: float) -> None:
        recorded_sleeps.append(s)

    # Fails twice with 429, succeeds on 3rd attempt
    provider = FaultyProvider(failure_mode="rate_limit", fail_times=2)

    result = execute_with_retry(
        provider,
        system="sys",
        user="usr",
        schema=MODEL_SCHEMA,
        max_attempts=3,
        base_backoff_s=2.0,
        jitter=False,
        sleep_fn=mock_sleep,
    )

    assert result is not None
    assert provider.call_count == 3
    assert len(recorded_sleeps) == 2
    # Base 2.0s exponential backoff without jitter: attempt 1 -> 2.0s, attempt 2 -> 4.0s
    assert recorded_sleeps[0] == 2.0
    assert recorded_sleeps[1] == 4.0


@pytest.mark.gate2
def test_retry_matrix_429_honors_retry_after() -> None:
    """Row 1: 429 rate limit honors explicit Retry-After header."""
    recorded_sleeps: list[float] = []

    def mock_sleep(s: float) -> None:
        recorded_sleeps.append(s)

    # Simulates provider returning 429 with retry_after=7.5
    provider = FaultyProvider(failure_mode="rate_limit", fail_times=1, retry_after=7.5)

    result = execute_with_retry(
        provider,
        system="sys",
        user="usr",
        schema=MODEL_SCHEMA,
        max_attempts=3,
        sleep_fn=mock_sleep,
    )

    assert result is not None
    assert provider.call_count == 2
    assert len(recorded_sleeps) == 1
    assert recorded_sleeps[0] == 7.5


@pytest.mark.gate2
def test_retry_matrix_429_exhaustion() -> None:
    """Row 1: 429 rate limit exhausts after max_attempts and raises RetryExhaustedError."""
    recorded_sleeps: list[float] = []

    provider = FaultyProvider(failure_mode="rate_limit", fail_times=3)

    with pytest.raises(RetryExhaustedError) as exc_info:
        execute_with_retry(
            provider,
            system="sys",
            user="usr",
            schema=MODEL_SCHEMA,
            max_attempts=3,
            sleep_fn=recorded_sleeps.append,
        )

    assert provider.call_count == 3
    assert len(recorded_sleeps) == 2
    assert "retries exhausted" in str(exc_info.value)


@pytest.mark.gate2
def test_retry_matrix_5xx_server_error() -> None:
    """Row 1: 5xx server errors retry and recover or exhaust."""
    recorded_sleeps: list[float] = []

    provider = FaultyProvider(failure_mode="server_error", fail_times=1)

    result = execute_with_retry(
        provider,
        system="sys",
        user="usr",
        schema=MODEL_SCHEMA,
        max_attempts=3,
        sleep_fn=recorded_sleeps.append,
    )

    assert result is not None
    assert provider.call_count == 2
    assert len(recorded_sleeps) == 1


@pytest.mark.gate2
def test_retry_matrix_truncated_output_signal_and_split() -> None:
    """Row 2: Truncated output signals truncation or invokes split_fn."""
    # Without split_fn: raises TruncatedOutputError signal
    provider = FaultyProvider(failure_mode="truncated", fail_times=1)
    with pytest.raises(TruncatedOutputError):
        execute_with_retry(
            provider,
            system="sys",
            user="usr",
            schema=MODEL_SCHEMA,
        )
    assert provider.call_count == 1

    # With split_fn: executes split re-run
    split_called = False

    def split_handler() -> dict[str, object]:
        nonlocal split_called
        split_called = True
        return {"mentions": [], "relationships": [], "events": [], "notes": ["split_recovered"]}

    provider2 = FaultyProvider(failure_mode="truncated", fail_times=1)
    res = execute_with_retry(
        provider2,
        system="sys",
        user="usr",
        schema=MODEL_SCHEMA,
        split_fn=split_handler,
    )

    assert split_called is True
    assert res["notes"] == ["split_recovered"]


@pytest.mark.gate2
def test_retry_matrix_schema_violation_recovers_on_single_retry() -> None:
    """Row 3: Schema invalid allows exactly 1 retry of that chunk and recovers."""
    provider = FaultyProvider(failure_mode="schema_violation", fail_times=1)

    result = execute_with_retry(
        provider,
        system="sys",
        user="usr",
        schema=MODEL_SCHEMA,
    )

    assert result is not None
    # 1 initial failure + 1 retry = 2 calls
    assert provider.call_count == 2


@pytest.mark.gate2
def test_retry_matrix_schema_violation_fails_after_single_retry() -> None:
    """Row 3: Schema invalid raises SchemaViolationError after exactly 1 retry."""
    provider = FaultyProvider(failure_mode="schema_violation", fail_times=2)

    with pytest.raises(SchemaViolationError):
        execute_with_retry(
            provider,
            system="sys",
            user="usr",
            schema=MODEL_SCHEMA,
        )

    # Exactly 2 calls (initial + 1 retry), never more
    assert provider.call_count == 2


@pytest.mark.gate2
def test_retry_matrix_refusal_zero_retries() -> None:
    """Row 4: Refusal/safety block makes 0 retries and fails fast."""
    provider = FaultyProvider(failure_mode="refusal", fail_times=5)

    with pytest.raises(RefusalError):
        execute_with_retry(
            provider,
            system="sys",
            user="usr",
            schema=MODEL_SCHEMA,
        )

    # Strictly 1 call (0 retries)
    assert provider.call_count == 1


@pytest.mark.gate2
def test_retry_matrix_401_auth_error_zero_retries_secret_safe() -> None:
    """Row 5: 401/403 makes 0 retries and emits secret-safe error message."""
    provider = FaultyProvider(failure_mode="auth_error", fail_times=5)

    with pytest.raises(AuthError) as exc_info:
        execute_with_retry(
            provider,
            system="sys",
            user="usr",
            schema=MODEL_SCHEMA,
        )

    # Strictly 1 call (0 retries)
    assert provider.call_count == 1
    err_msg = str(exc_info.value)
    assert "401/403" in err_msg
    # Ensure no secrets leak
    assert "sk-" not in err_msg
    assert "secret" not in err_msg.lower() or "check credentials" in err_msg.lower()
