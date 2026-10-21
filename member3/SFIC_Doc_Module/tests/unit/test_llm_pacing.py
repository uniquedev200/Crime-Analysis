"""Gate 2 unit tests for LLM pacing, Retry-After parsing, and single-layer retries."""

from __future__ import annotations

import pytest

from atlas.errors import RetryExhaustedError
from atlas.llm.pacing import RateLimiter, parse_retry_after
from atlas.llm.retry import RateLimitError, execute_with_retry


class _FakeClock:
    """Deterministic clock + sleep recorder for pacing tests."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.gate2
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("6s", 6.0),
        ("1m30s", 90.0),
        ("500ms", 0.5),
        ("2 min", 120.0),
        ("1h", 3600.0),
        ("12", 12.0),
        ("7.5", 7.5),
        (7.5, 7.5),
        (3, 3.0),
        (None, None),
        ("", None),
        ("not-a-duration", None),
    ],
)
def test_parse_retry_after_suffixes(header: object, expected: float | None) -> None:
    """Provider duration suffixes ('6s', '1m30s') and plain numbers parse without error."""
    assert parse_retry_after(header) == expected


@pytest.mark.gate2
def test_parse_retry_after_http_date() -> None:
    """An HTTP-date Retry-After yields a positive number of seconds."""
    value = parse_retry_after("Wed, 21 Oct 2099 07:28:00 GMT")
    assert value is not None
    assert value > 0


@pytest.mark.gate2
def test_rate_limiter_enforces_min_interval() -> None:
    """A minimum interval paces consecutive requests instead of firing immediately."""
    clock = _FakeClock()
    limiter = RateLimiter(
        max_requests=0,
        min_interval_s=2.0,
        sleep_fn=clock.sleep,
        clock_fn=clock.clock,
    )
    assert limiter.acquire() == 0.0
    assert limiter.acquire() == 2.0
    assert clock.sleeps == [2.0]


@pytest.mark.gate2
def test_rate_limiter_sliding_window() -> None:
    """The sliding window blocks once the per-window request budget is reached."""
    clock = _FakeClock()
    limiter = RateLimiter(
        max_requests=2,
        window_s=60.0,
        min_interval_s=0.0,
        sleep_fn=clock.sleep,
        clock_fn=clock.clock,
    )
    limiter.acquire()
    limiter.acquire()
    waited = limiter.acquire()
    assert waited == 60.0
    assert clock.sleeps == [60.0]


@pytest.mark.gate2
def test_rate_limiter_honors_retry_after_signal() -> None:
    """A provider-signalled wait blocks the next request by that amount."""
    clock = _FakeClock()
    limiter = RateLimiter(max_requests=0, min_interval_s=0.0, sleep_fn=clock.sleep, clock_fn=clock.clock)
    limiter.notify_retry_after(5.0)
    assert limiter.acquire() == 5.0


@pytest.mark.gate2
def test_rate_limiter_derives_interval_from_budget() -> None:
    """When no explicit interval is given it is derived from requests-per-minute."""
    limiter = RateLimiter.from_settings(max_requests_per_minute=30, min_interval_s=0.0)
    assert limiter.min_interval_s == 2.0


class _ReturningClientWithOwnRetries:
    """Client that owns its retry loop (like the real provider adapters)."""

    handles_retries = True

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, system: str, user: str, schema: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return {"mentions": [], "relationships": [], "events": [], "notes": []}


class _FailingClientWithOwnRetries:
    """Client owning its retry loop that always exhausts its own retries."""

    handles_retries = True

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, system: str, user: str, schema: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        raise RetryExhaustedError("inner retries exhausted")


@pytest.mark.gate2
def test_execute_with_retry_does_not_double_wrap_retrying_clients() -> None:
    """A client that owns its retries is called exactly once (no nested 3x3 burst)."""
    client = _ReturningClientWithOwnRetries()
    result = execute_with_retry(client, system="s", user="u", schema={}, max_attempts=3)
    assert result["mentions"] == []
    assert client.calls == 1


@pytest.mark.gate2
def test_execute_with_retry_does_not_multiply_exhausted_inner_retries() -> None:
    """An exhausted inner retry loop is not retried again by the outer loop."""
    client = _FailingClientWithOwnRetries()
    with pytest.raises(RetryExhaustedError):
        execute_with_retry(client, system="s", user="u", schema={}, max_attempts=3, sleep_fn=lambda _s: None)
    assert client.calls == 1


class _TransientClientWithoutRetries:
    """Client with no internal retry loop; the wrapper must retry it."""

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, system: str, user: str, schema: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        if self.calls == 1:
            raise RateLimitError("429", retry_after=0.0)
        return {"mentions": [], "relationships": [], "events": [], "notes": []}


@pytest.mark.gate2
def test_execute_with_retry_still_retries_clients_without_own_retries() -> None:
    """Clients that do not own retries keep the wrapper's retry behaviour."""
    client = _TransientClientWithoutRetries()
    result = execute_with_retry(client, system="s", user="u", schema={}, max_attempts=3, sleep_fn=lambda _s: None)
    assert result["mentions"] == []
    assert client.calls == 2
