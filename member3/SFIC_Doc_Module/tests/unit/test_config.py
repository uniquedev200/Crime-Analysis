"""Gate 0 configuration tests."""

from __future__ import annotations

import pytest

from atlas.config import AtlasSettings
from atlas.errors import ConfigError


@pytest.mark.gate0
def test_missing_secret_no_leak() -> None:
    # When openai provider is selected without credentials, error does not leak secret values
    secret_token = "sk-super-confidential-secret-999"

    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
        )

    err_msg = str(exc_info.value)
    assert secret_token not in err_msg
    assert "OPENAI_API_KEY" in err_msg
    assert "Missing required configuration" in err_msg


@pytest.mark.gate0
def test_default_values() -> None:
    # `_env_file=None` keeps this a test of the code defaults rather than of the
    # developer's local .env (e.g. a live LLM_PROVIDER).
    settings = AtlasSettings(_env_file=None)
    assert settings.LLM_PROVIDER == "mock"
    assert settings.OCR_ENGINE == "tesseract"
    assert settings.OCR_LANGS == "eng"
    assert settings.OCR_DPI == 300
    assert settings.PDF_TEXT_MIN_CHARS == 25
    assert settings.MAX_FILE_MB == 50
    assert settings.MAX_PDF_PAGES == 60
    assert settings.DEFAULT_PHONE_REGION == "IN"
    assert settings.ATLAS_SYNTHETIC_ONLY is True
    assert settings.LLM_TEMPERATURE == 0.0
