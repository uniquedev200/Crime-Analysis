from __future__ import annotations


class AtlasError(Exception):
    """Base exception for all ATLAS errors."""


class ConfigError(AtlasError):
    """Raised when configuration is invalid or missing required values."""


class IntegrityError(AtlasError):
    """Raised when file integrity or hash check fails."""


class RejectedInputError(AtlasError):
    """Raised when an input document or file is rejected before or during processing."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OcrLanguageUnavailable(AtlasError):
    """Raised when a requested OCR language pack is not installed or available."""

    def __init__(self, lang: str) -> None:
        super().__init__(f"OCR language pack unavailable: {lang}")
        self.lang = lang


class SchemaViolationError(AtlasError):
    """Raised when schema validation fails."""


class ProviderError(AtlasError):
    """Raised on LLM or external service provider failure."""


class RetryExhaustedError(ProviderError):
    """Raised when retries have been exhausted for a provider request."""


class AuthorizationError(AtlasError):
    """Raised when an unauthorized action or case access is attempted."""


__all__ = [
    "AtlasError",
    "AuthorizationError",
    "ConfigError",
    "IntegrityError",
    "OcrLanguageUnavailable",
    "ProviderError",
    "RejectedInputError",
    "RetryExhaustedError",
    "SchemaViolationError",
]
