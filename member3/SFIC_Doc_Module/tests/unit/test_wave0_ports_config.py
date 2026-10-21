from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from atlas.__main__ import main
from atlas.config import AtlasSettings, get_settings
from atlas.errors import (
    AtlasError,
    AuthorizationError,
    ConfigError,
    IntegrityError,
    OcrLanguageUnavailable,
    ProviderError,
    RejectedInputError,
    RetryExhaustedError,
    SchemaViolationError,
)
from atlas.logging_setup import (
    PiiScrubFilter,
    clear_registered_secrets,
    register_secret,
    setup_logging,
)
from atlas.ports import (
    EntityStorePort,
    GraphSinkPort,
    LlmClientPort,
    OcrEnginePort,
    PdfBackendPort,
)
from atlas.version import (
    NORMALIZATION_VERSION,
    PIPELINE_VERSION,
    PROMPT_VERSION,
    RESOLVER_VERSION,
    SCHEMA_VERSION,
)


@pytest.mark.gate0
def test_version_constants() -> None:
    assert PIPELINE_VERSION == "0.1.0"
    assert SCHEMA_VERSION == "1.0.0"
    assert PROMPT_VERSION == "extract-v1"
    assert NORMALIZATION_VERSION == "1"
    assert RESOLVER_VERSION == "1"


@pytest.mark.gate0
def test_error_hierarchy() -> None:
    assert issubclass(ConfigError, AtlasError)
    assert issubclass(IntegrityError, AtlasError)
    assert issubclass(RejectedInputError, AtlasError)
    assert issubclass(OcrLanguageUnavailable, AtlasError)
    assert issubclass(SchemaViolationError, AtlasError)
    assert issubclass(ProviderError, AtlasError)
    assert issubclass(RetryExhaustedError, ProviderError)
    assert issubclass(AuthorizationError, AtlasError)

    rej = RejectedInputError("file size exceeds limit")
    assert rej.reason == "file size exceeds limit"
    assert str(rej) == "file size exceeds limit"

    ocr_err = OcrLanguageUnavailable("tam")
    assert ocr_err.lang == "tam"
    assert "tam" in str(ocr_err)


@pytest.mark.gate0
def test_ports_protocols() -> None:
    class DummyEntityStore:
        def query_candidates(self, auth: Any, identifier_keys: list[str], name_keys: list[str]) -> list[dict[str, Any]]:
            return []

        def store_mentions(self, case_id: str, mentions: list[Any]) -> None:
            pass

        def store_suggestions(self, case_id: str, suggestions: list[Any]) -> None:
            pass

        def record_action(self, action: Any) -> None:
            pass

        def verify_chain(self) -> bool:
            return True

    class DummyGraphSink:
        def push_nodes(self, nodes: list[dict[str, Any]]) -> None:
            pass

        def push_edges(self, edges: list[dict[str, Any]]) -> None:
            pass

    class DummyLlmClient:
        @property
        def provider_name(self) -> str:
            return "mock"

        @property
        def model_name(self) -> str:
            return "test-model"

        def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
            return {}

    class DummyOcrEngine:
        @property
        def engine_name(self) -> str:
            return "tesseract"

        @property
        def engine_version(self) -> str:
            return "5.3.0"

        def recognize(self, image: Any, langs: list[str]) -> Any:
            return {}

    class DummyPdfBackend:
        def extract_text(self, path: Path, page: int) -> str:
            return "sample text"

        def page_count(self, path: Path) -> int:
            return 1

        def render_page(self, path: Path, page: int, dpi: int) -> Any:
            return None

        def is_encrypted(self, path: Path) -> bool:
            return False

    assert isinstance(DummyEntityStore(), EntityStorePort)
    assert isinstance(DummyGraphSink(), GraphSinkPort)
    assert isinstance(DummyLlmClient(), LlmClientPort)
    assert isinstance(DummyOcrEngine(), OcrEnginePort)
    assert isinstance(DummyPdfBackend(), PdfBackendPort)


@pytest.mark.gate0
def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DEV2_TOKEN", raising=False)
    # `_env_file=None` keeps this a test of the code defaults rather than of the
    # developer's local .env (e.g. a live LLM_PROVIDER).
    settings = AtlasSettings(_env_file=None)
    assert settings.LLM_PROVIDER == "mock"
    assert settings.LLM_MODEL == ""
    assert settings.OPENAI_API_KEY is None
    assert settings.GEMINI_API_KEY is None
    assert settings.LLM_TEMPERATURE == 0.0
    assert settings.LLM_TIMEOUT_S == 60.0
    assert settings.LLM_MAX_ATTEMPTS == 3
    assert settings.LLM_CHUNK_CHARS == 12000
    assert settings.MAX_LLM_CALLS_PER_RUN == 40
    assert settings.OCR_ENGINE == "tesseract"
    assert settings.OCR_LANGS == "eng"
    assert settings.OCR_DPI == 300
    assert settings.OCR_PSM == 3
    assert settings.ATLAS_REQUIRE_TESSERACT is True
    assert settings.OCR_ID_AUTOTRUST_MIN_CONF is None
    assert settings.PDF_TEXT_MIN_CHARS == 25
    assert settings.MAX_FILE_MB == 50
    assert settings.MAX_PDF_PAGES == 60
    assert settings.MAX_IMAGE_PIXELS == 60_000_000
    assert settings.XLSX_FULL_LOAD_MB == 15
    assert settings.DEFAULT_PHONE_REGION == "IN"
    assert settings.DATA_DIR == "./data"
    assert settings.OUTPUT_DIR == "./outputs"
    assert settings.ATLAS_SYNTHETIC_ONLY is True
    assert settings.DEV2_BASE_URL == ""
    assert settings.DEV2_TOKEN is None


@pytest.mark.gate0
def test_config_singleton() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


@pytest.mark.gate0
def test_config_missing_secret_safe_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(LLM_PROVIDER="openai", OPENAI_API_KEY=None)
    assert "OPENAI_API_KEY" in str(exc_info.value)
    # Ensure error message does not leak secret values
    assert "sk-" not in str(exc_info.value)

    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(LLM_PROVIDER="gemini", GEMINI_API_KEY=None)
    assert "GEMINI_API_KEY" in str(exc_info.value)

    # Valid secret does not raise
    s = AtlasSettings(LLM_PROVIDER="openai", OPENAI_API_KEY=SecretStr("sk-test-secret-12345"))
    assert s.OPENAI_API_KEY is not None
    assert s.OPENAI_API_KEY.get_secret_value() == "sk-test-secret-12345"
    assert "sk-test-secret-12345" not in repr(s)


@pytest.mark.gate0
def test_config_ignores_extra() -> None:
    # extra="ignore" means unknown fields are silently discarded (needed for .env vars like PYTHONUTF8)
    s = AtlasSettings(**{"UNKNOWN_SETTING_FIELD": "value"})  # type: ignore[arg-type]
    assert not hasattr(s, "UNKNOWN_SETTING_FIELD")


@pytest.mark.gate0
def test_logging_scrubber_redacts_digits_and_secrets() -> None:
    clear_registered_secrets()
    sensitive_token = "TOP_SECRET_AUTH_TOKEN_99"
    register_secret(sensitive_token)

    scrubber = PiiScrubFilter()

    # Digits >= 6 must be redacted
    assert scrubber.scrub("Phone: 9876543210") == "Phone: [REDACTED]"
    assert scrubber.scrub("IMEI: 123456789012345") == "IMEI: [REDACTED]"

    # Digits < 6 must be preserved
    assert scrubber.scrub("Count: 12345") == "Count: 12345"
    assert scrubber.scrub("Port 8000 status 200") == "Port 8000 status 200"

    # Registered secret must be redacted
    assert scrubber.scrub(f"Bearer {sensitive_token}") == "Bearer [REDACTED]"

    # Instance-specific secret
    inst_filter = PiiScrubFilter(secrets=["INSTANCE_SECRET_XYZ"])
    assert inst_filter.scrub("Key: INSTANCE_SECRET_XYZ") == "Key: [REDACTED]"

    # Test via logging framework
    logger = logging.getLogger("atlas.test.scrubber")
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(scrubber)
    logger.addHandler(handler)

    try:
        logger.info("FIR suspect phone %s and secret %s", "9988776655", sensitive_token)
        handler.flush()
        output = stream.getvalue()
        assert "9988776655" not in output
        assert sensitive_token not in output
        assert "[REDACTED]" in output
    finally:
        logger.removeHandler(handler)
        clear_registered_secrets()


@pytest.mark.gate0
def test_setup_logging_initialization() -> None:
    setup_logging(level="DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert any(isinstance(f, PiiScrubFilter) for f in root.filters) or any(
        any(isinstance(f, PiiScrubFilter) for f in h.filters) for h in root.handlers
    )


@pytest.mark.gate0
def test_cli_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    subcommands = [
        "run",
        "status",
        "results",
        "demo",
        "eval",
        "llm-smoke",
        "confirm-profile",
    ]

    for cmd in subcommands:
        try:
            ret = main([cmd, "--help"])
            assert ret == 0
        except SystemExit as e:
            assert e.code == 0
        captured = capsys.readouterr()
        assert f"usage: atlas {cmd}" in captured.out or f"atlas {cmd}" in captured.out

    # No args prints help
    ret = main([])
    assert ret == 0
    captured = capsys.readouterr()
    assert "usage: atlas" in captured.out or "Available subcommands" in captured.out
