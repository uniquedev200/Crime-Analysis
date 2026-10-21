"""Gate 2 unit tests for LLM client factory, secret safety, and MockProvider."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from atlas.config import AtlasSettings
from atlas.contracts.model_schema import MODEL_SCHEMA
from atlas.errors import ConfigError
from atlas.llm.client import get_llm_client
from atlas.llm.gemini_adapter import GeminiAdapter
from atlas.llm.mock import FaultyProvider, MockProvider
from atlas.llm.openai_adapter import OpenAiAdapter
from atlas.ports.llm import LlmClientPort


@pytest.mark.gate2
def test_client_factory_mock() -> None:
    """Verify factory returns MockProvider when provider is 'mock'."""
    settings = AtlasSettings(LLM_PROVIDER="mock")
    client = get_llm_client(settings)
    assert isinstance(client, MockProvider)
    assert client.provider_name == "mock"
    assert client.model_name == "scripted"
    assert isinstance(client, LlmClientPort)


@pytest.mark.gate2
def test_client_factory_faulty() -> None:
    """Verify factory returns FaultyProvider when provider is 'faulty'."""
    settings = AtlasSettings(LLM_PROVIDER="faulty")
    client = get_llm_client(settings)
    assert isinstance(client, FaultyProvider)
    assert client.provider_name == "faulty"
    assert isinstance(client, LlmClientPort)


@pytest.mark.gate2
def test_client_factory_openai_with_key() -> None:
    """Verify factory returns OpenAiAdapter when valid API key is provided."""
    settings = AtlasSettings(
        LLM_PROVIDER="openai",
        OPENAI_API_KEY=SecretStr("sk-test-secret-value-12345"),
        LLM_MODEL="gpt-4o-mini",
    )
    client = get_llm_client(settings)
    assert isinstance(client, OpenAiAdapter)
    assert client.provider_name == "openai"
    assert client.model_name == "gpt-4o-mini"
    assert isinstance(client, LlmClientPort)


@pytest.mark.gate2
def test_client_factory_gemini_with_key() -> None:
    """Verify factory returns GeminiAdapter when valid API key is provided."""
    settings = AtlasSettings(
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY=SecretStr("gemini-test-secret-value-67890"),
        LLM_MODEL="gemini-2.0-flash",
    )
    client = get_llm_client(settings)
    assert isinstance(client, GeminiAdapter)
    assert client.provider_name == "gemini"
    assert client.model_name == "gemini-2.0-flash"
    assert isinstance(client, LlmClientPort)


@pytest.mark.gate2
def test_client_factory_groq_with_key() -> None:
    """Verify factory returns OpenAiAdapter configured for Groq when valid API key is provided."""
    settings = AtlasSettings(
        LLM_PROVIDER="groq",
        GROQ_API_KEY=SecretStr("gsk-test-secret-value-12345"),
        LLM_MODEL="openai/gpt-oss-120b",
    )
    client = get_llm_client(settings)
    assert isinstance(client, OpenAiAdapter)
    assert client.provider_name == "groq"
    assert client.model_name == "openai/gpt-oss-120b"
    assert isinstance(client, LlmClientPort)


@pytest.mark.gate2
def test_client_factory_missing_secret_fails_safely_groq() -> None:
    """Verify missing GROQ_API_KEY raises ConfigError without leaking secrets."""
    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(LLM_PROVIDER="groq", GROQ_API_KEY=None, OPENAI_API_KEY=None)
    err_msg = str(exc_info.value)
    assert "GROQ_API_KEY must be configured" in err_msg


@pytest.mark.gate2
def test_client_factory_missing_secret_fails_safely_openai() -> None:
    """Verify missing OPENAI_API_KEY raises ConfigError without leaking secrets."""
    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(LLM_PROVIDER="openai", OPENAI_API_KEY=None)
    err_msg = str(exc_info.value)
    assert "OPENAI_API_KEY must be configured" in err_msg
    # Ensure no secret or partial token appears in error message
    assert "sk-" not in err_msg


@pytest.mark.gate2
def test_client_factory_missing_secret_fails_safely_gemini() -> None:
    """Verify missing GEMINI_API_KEY raises ConfigError without leaking secrets."""
    with pytest.raises(ConfigError) as exc_info:
        AtlasSettings(LLM_PROVIDER="gemini", GEMINI_API_KEY=None)
    err_msg = str(exc_info.value)
    assert "GEMINI_API_KEY must be configured" in err_msg


@pytest.mark.gate2
def test_client_factory_unsupported_provider() -> None:
    """Verify unsupported provider name raises ConfigError."""
    settings = AtlasSettings(LLM_PROVIDER="unsupported_vendor")
    with pytest.raises(ConfigError, match="Unsupported LLM_PROVIDER"):
        get_llm_client(settings)


@pytest.mark.gate2
def test_mock_provider_records_captured_prompts() -> None:
    """Verify MockProvider captures all prompt transmissions for audit/isolation assertions."""
    provider = MockProvider()
    assert len(provider.captured_prompts) == 0

    system_prompt = "You are a test extractor."
    user_prompt = "Case documents follow.\n[UNIT FIR_A:p001]\nAccused: Vikram Singh\n<<<UNITS-0123>>>"

    provider.extract(system_prompt, user_prompt, MODEL_SCHEMA)

    assert len(provider.captured_prompts) == 1
    captured = provider.captured_prompts[0]
    assert captured["system"] == system_prompt
    assert captured["user"] == user_prompt
    assert captured["schema"] == MODEL_SCHEMA


@pytest.mark.gate2
def test_mock_provider_reads_scripted_fixture() -> None:
    """Verify MockProvider loads and returns validated model output from recorded fixtures."""
    provider = MockProvider()
    user_prompt = "Case documents follow.\n[UNIT FIR_A:p001]\nAccused: Vikram Singh alias Vicky"
    res = provider.extract("system", user_prompt, MODEL_SCHEMA)

    assert isinstance(res, dict)
    assert "mentions" in res
    assert "relationships" in res
    assert "events" in res
    assert "notes" in res
    # Should contain facts from FIR_A page 1
    assert any(m["surface_text"] == "Vikram Singh" for m in res["mentions"])


@pytest.mark.gate2
def test_mock_provider_custom_registration() -> None:
    """Verify MockProvider custom response registration."""
    provider = MockProvider()
    custom_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Custom Person",
                "role_stated": "witness",
                "unit_id": "CUSTOM-DOC:p001",
                "quote": "Witness Custom Person",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": ["custom"],
    }
    provider.register_response("CUSTOM-DOC", 0, custom_output)

    res = provider.extract("sys", "[UNIT CUSTOM-DOC:p001]\nWitness Custom Person", MODEL_SCHEMA)
    assert res["mentions"][0]["surface_text"] == "Custom Person"
