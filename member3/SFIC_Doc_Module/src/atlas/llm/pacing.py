"""Client-side rate limiting and provider pacing for LLM calls.

Fixes the "zero pacing" failure mode by enforcing a configurable sliding-window
request budget (e.g. Groq's 30 requests/minute) and a minimum interval between
calls. Also parses provider rate-limit headers that use duration suffixes such as
``6s`` or ``1m30s`` (which plain ``float()`` rejects).

Nothing here hardcodes a provider limit: all values come from configuration.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

_DURATION_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>ms|h|hr|hrs|m|min|mins|s|sec|secs)", re.IGNORECASE)
_UNIT_SECONDS: dict[str, float] = {
    "ms": 0.001,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
}


def parse_retry_after(value: object) -> float | None:
    """Parse a provider Retry-After / rate-limit reset header into seconds.

    Accepts plain numbers ("12", "7.5"), duration strings ("6s", "1m30s",
    "500ms", "2 min"), and HTTP-date strings. Returns ``None`` when the value
    cannot be interpreted. Never raises.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0.0, float(value))

    text = str(value).strip()
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    total = 0.0
    matched = False
    for match in _DURATION_RE.finditer(text):
        matched = True
        total += float(match.group("value")) * _UNIT_SECONDS[match.group("unit").lower()]
    if matched:
        return total

    # HTTP-date form (RFC 7231 Retry-After allows a date).
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(text)
        if dt is not None:
            now = time.time()
            ts = dt.timestamp()
            return max(0.0, ts - now)
    except (TypeError, ValueError, OverflowError):
        pass

    return None


@dataclass
class RateLimiter:
    """Sliding-window request limiter with a minimum inter-request interval.

    Args:
        max_requests: Maximum requests allowed per ``window_s`` (0 disables the window).
        window_s: Sliding window length in seconds.
        min_interval_s: Minimum spacing between consecutive requests (0 disables).
        sleep_fn: Injectable sleep function (for tests).
        clock_fn: Injectable monotonic clock (for tests).
    """

    max_requests: int = 0
    window_s: float = 60.0
    min_interval_s: float = 0.0
    sleep_fn: Callable[[float], None] = time.sleep
    clock_fn: Callable[[], float] = time.monotonic
    _call_times: list[float] = field(default_factory=list)
    _last_call: float | None = None
    _blocked_until: float = 0.0

    @classmethod
    def from_settings(
        cls,
        max_requests_per_minute: int,
        min_interval_s: float = 0.0,
        window_s: float = 60.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> RateLimiter:
        """Build a limiter from configuration values.

        When ``min_interval_s`` is not positive it is derived from the request
        budget (``window_s / max_requests_per_minute``) so a 30 RPM budget yields
        a 2-second minimum spacing automatically.
        """
        effective_interval = min_interval_s
        if effective_interval <= 0.0 and max_requests_per_minute > 0:
            effective_interval = window_s / max_requests_per_minute
        return cls(
            max_requests=max_requests_per_minute,
            window_s=window_s,
            min_interval_s=effective_interval,
            sleep_fn=sleep_fn,
            clock_fn=clock_fn,
        )

    def notify_retry_after(self, seconds: float | None) -> None:
        """Record a provider-signalled wait so the next call respects it."""
        if seconds is None or seconds <= 0:
            return
        self._blocked_until = max(self._blocked_until, self.clock_fn() + float(seconds))

    def acquire(self) -> float:
        """Block until a request is allowed. Returns total seconds slept."""
        total_slept = 0.0

        # 1. Minimum interval since the last call.
        now = self.clock_fn()
        if self._last_call is not None and self.min_interval_s > 0:
            earliest = self._last_call + self.min_interval_s
            if earliest > now:
                waited = earliest - now
                self.sleep_fn(waited)
                total_slept += waited
                now = self.clock_fn()

        # 2. Sliding-window budget.
        if self.max_requests > 0:
            while True:
                now = self.clock_fn()
                self._call_times = [t for t in self._call_times if now - t < self.window_s]
                if len(self._call_times) < self.max_requests:
                    break
                wait_for = self.window_s - (now - self._call_times[0])
                if wait_for > 0:
                    self.sleep_fn(wait_for)
                    total_slept += wait_for

        # 3. Provider-signalled block (e.g. from a prior 429 Retry-After).
        now = self.clock_fn()
        if self._blocked_until > now:
            waited = self._blocked_until - now
            self.sleep_fn(waited)
            total_slept += waited
            now = self.clock_fn()
        self._blocked_until = 0.0

        self._call_times.append(self.clock_fn())
        self._last_call = self.clock_fn()
        return total_slept


__all__ = ["RateLimiter", "parse_retry_after"]
