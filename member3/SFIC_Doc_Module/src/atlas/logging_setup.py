from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import SecretStr

_registered_secrets: set[str] = set()
_DIGITS_RE = re.compile(r"\d{6,}")


def register_secret(secret: str | SecretStr | None) -> None:
    """Register a secret string or SecretStr to be scrubbed from all logs."""
    if secret is None:
        return
    val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    val = val.strip()
    if val:
        _registered_secrets.add(val)


def clear_registered_secrets() -> None:
    """Clear all globally registered secrets (useful in tests)."""
    _registered_secrets.clear()


class PiiScrubFilter(logging.Filter):
    """Logging filter that redacts digit runs >= 6 and registered secrets to prevent PII leakage."""

    def __init__(
        self,
        name: str = "",
        secrets: Iterable[str | SecretStr] | None = None,
    ) -> None:
        super().__init__(name=name)
        self._instance_secrets: set[str] = set()
        if secrets:
            for s in secrets:
                self.register_secret(s)

    def register_secret(self, secret: str | SecretStr | None) -> None:
        """Register a secret on this filter instance."""
        if secret is None:
            return
        val = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
        val = val.strip()
        if val:
            self._instance_secrets.add(val)

    def scrub(self, text: str) -> str:
        """Scrub digit runs >= 6 and registered secrets from text."""
        if not text:
            return text

        all_secrets = _registered_secrets | self._instance_secrets
        # Redact longer secrets first to avoid partial replacements
        for secret in sorted(all_secrets, key=len, reverse=True):
            if secret in text:
                text = text.replace(secret, "[REDACTED]")

        # Redact any contiguous sequence of 6 or more digits
        text = _DIGITS_RE.sub("[REDACTED]", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub record message and exception text in place."""
        try:
            msg = record.getMessage()
            record.msg = self.scrub(msg)
            record.args = ()
            if record.exc_text:
                record.exc_text = self.scrub(record.exc_text)
        except Exception:
            pass
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure PII-free logging using standard logging module and PiiScrubFilter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Try registering secrets from settings if configured
    try:
        from atlas.config import get_settings

        settings = get_settings()
        if settings.OPENAI_API_KEY:
            register_secret(settings.OPENAI_API_KEY)
        if settings.GEMINI_API_KEY:
            register_secret(settings.GEMINI_API_KEY)
        if settings.DEV2_TOKEN:
            register_secret(settings.DEV2_TOKEN)
    except Exception:
        pass

    scrub_filter = PiiScrubFilter()

    # Add filter to root logger
    if not any(isinstance(f, PiiScrubFilter) for f in root_logger.filters):
        root_logger.addFilter(scrub_filter)

    # Configure default StreamHandler if no handlers present
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)
        handler.addFilter(scrub_filter)
        root_logger.addHandler(handler)
    else:
        for h in root_logger.handlers:
            if not any(isinstance(f, PiiScrubFilter) for f in h.filters):
                h.addFilter(scrub_filter)


__all__ = [
    "PiiScrubFilter",
    "clear_registered_secrets",
    "register_secret",
    "setup_logging",
]
