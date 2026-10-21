"""Gate 0 logging scrubber tests."""

from __future__ import annotations

import logging

import pytest

from atlas.logging_setup import PiiScrubFilter, clear_registered_secrets, register_secret


@pytest.mark.gate0
def test_scrubber_redacts_digits() -> None:
    f = PiiScrubFilter()
    # 10-digit phone number
    message = "Contact number is 9876543210 for caller"
    scrubbed = f.scrub(message)
    assert scrubbed == "Contact number is [REDACTED] for caller"

    # 15-digit IMEI
    imei_msg = "Device IMEI 123456789012345 detected"
    assert f.scrub(imei_msg) == "Device IMEI [REDACTED] detected"


@pytest.mark.gate0
def test_scrubber_preserves_short() -> None:
    f = PiiScrubFilter()
    # 5-digit zip code or count should not be redacted
    short_msg = "PIN 11001 with 123 items and 42 pages"
    scrubbed = f.scrub(short_msg)
    assert scrubbed == "PIN 11001 with 123 items and 42 pages"


@pytest.mark.gate0
def test_scrubber_redacts_registered_secrets() -> None:
    clear_registered_secrets()
    secret_val = "sk-proj-super-secret-token-xyz"
    register_secret(secret_val)

    try:
        f = PiiScrubFilter()
        log_record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg=f"Using token {secret_val} for authentication",
            args=(),
            exc_info=None,
        )
        f.filter(log_record)
        assert secret_val not in log_record.msg
        assert "[REDACTED]" in log_record.msg
    finally:
        clear_registered_secrets()
