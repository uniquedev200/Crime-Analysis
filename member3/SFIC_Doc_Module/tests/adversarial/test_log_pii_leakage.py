"""Adversarial test suite: Logging PII leakage prevention and secret token redaction.

Tests coverage:
1. Redaction of phone numbers (10 digits).
2. Redaction of IMEIs (14-16 digits) and Aadhaar/Account numbers (12+ digits).
3. Redaction of registered secret API tokens and bearer credentials.
4. Logging handler integration scrubbing record.msg and record.args when feeding PII into logger.
5. Scrubbing of exception text (record.exc_text) when present on LogRecord.
"""

from __future__ import annotations

import io
import logging

import pytest

from atlas.logging_setup import (
    PiiScrubFilter,
    clear_registered_secrets,
    register_secret,
)

pytestmark = pytest.mark.gate5


@pytest.fixture(autouse=True)
def clean_secrets() -> None:
    """Ensure registered secrets are cleared before and after each test."""
    clear_registered_secrets()
    yield
    clear_registered_secrets()


@pytest.mark.gate5
def test_pii_filter_redacts_phone_numbers() -> None:
    """Any sequence of 6 or more consecutive digits (such as 10-digit phone numbers) is redacted."""
    filter_inst = PiiScrubFilter()

    test_cases = [
        ("Calling 9876543210 regarding the case", "Calling [REDACTED] regarding the case"),
        ("Phone: +91-9876543210 (verified)", "Phone: +91-[REDACTED] (verified)"),
        ("Contact numbers: 9112233445 and 9988776655", "Contact numbers: [REDACTED] and [REDACTED]"),
        ("5 digits 12345 preserved", "5 digits 12345 preserved"),
        ("Exact 6 digits 123456 redacted", "Exact 6 digits [REDACTED] redacted"),
    ]

    for raw, expected in test_cases:
        scrubbed = filter_inst.scrub(raw)
        assert scrubbed == expected
        assert "9876543210" not in scrubbed


@pytest.mark.gate5
def test_pii_filter_redacts_imei_and_bank_account_numbers() -> None:
    """14 to 16 digit IMEIs and 11 to 16 digit bank accounts are redacted to [REDACTED]."""
    filter_inst = PiiScrubFilter()

    # 15-digit IMEI
    imei_text = "Target IMEI device was 860123456789012 at cell tower."
    scrubbed_imei = filter_inst.scrub(imei_text)
    assert "860123456789012" not in scrubbed_imei
    assert "[REDACTED]" in scrubbed_imei

    # 12-digit Aadhaar / Account
    account_text = "Funds transferred to account 912345678901 via NEFT."
    scrubbed_account = filter_inst.scrub(account_text)
    assert "912345678901" not in scrubbed_account
    assert "[REDACTED]" in scrubbed_account


@pytest.mark.gate5
def test_pii_filter_redacts_registered_secret_tokens() -> None:
    """Registered secrets (API keys, bearer tokens) are replaced with [REDACTED]."""
    openai_key = "sk-proj-supersecretkey999abc111"
    bearer_token = "DEV2_BEARER_AUTH_TOKEN_SECRET_XYZ"

    register_secret(openai_key)
    register_secret(bearer_token)

    filter_inst = PiiScrubFilter()

    sensitive_log = f"Failed authenticating to API using key {openai_key}; token {bearer_token}"
    scrubbed = filter_inst.scrub(sensitive_log)

    assert openai_key not in scrubbed
    assert bearer_token not in scrubbed
    assert scrubbed == "Failed authenticating to API using key [REDACTED]; token [REDACTED]"


@pytest.mark.gate5
def test_logger_stream_handler_scrubs_pii_and_secrets() -> None:
    """Feeding phone numbers, IMEIs, and secret tokens into logger results in [REDACTED] output."""
    secret_key = "SECRET_API_TOKEN_9999"
    phone_number = "9876543210"
    imei = "860123456789012"
    register_secret(secret_key)

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    scrub_filter = PiiScrubFilter()
    handler.addFilter(scrub_filter)

    test_logger = logging.getLogger("atlas.test.redteam_feed")
    test_logger.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)
    test_logger.propagate = False

    try:
        # Feed phone number and secret token as formatting arguments
        test_logger.info("Suspect phone %s used secret token %s", phone_number, secret_key)

        # Feed IMEI in direct string message
        test_logger.warning("IMEI detected: %s at cell tower", imei)

        output = log_stream.getvalue()

        # Sensitive phone number, IMEI, and secret token must NEVER appear in output
        assert phone_number not in output
        assert secret_key not in output
        assert imei not in output
        assert "[REDACTED]" in output

        # Assert direct LogRecord exception text scrubbing
        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg="An error occurred",
            args=(),
            exc_info=None,
        )
        record.exc_text = f"Traceback with phone {phone_number} and key {secret_key}"
        scrub_filter.filter(record)
        assert phone_number not in record.exc_text
        assert secret_key not in record.exc_text
        assert "[REDACTED]" in record.exc_text

    finally:
        test_logger.removeHandler(handler)
        handler.close()
