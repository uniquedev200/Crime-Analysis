"""Gate 2 unit tests for OpenAI and Gemini adapters using mock SDK clients."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import openai
import pytest
from google.genai import errors as genai_errors

from atlas.contracts.model_schema import MODEL_SCHEMA
from atlas.errors import RetryExhaustedError, SchemaViolationError
from atlas.llm.gemini_adapter import GeminiAdapter, convert_schema_for_gemini
from atlas.llm.openai_adapter import OpenAiAdapter
from atlas.llm.retry import (
    AuthError,
    RateLimitError,
    RefusalError,
    ServerError,
    TruncatedOutputError,
)

SAMPLE_MODEL_RESPONSE = {
    "mentions": [
        {
            "local_id": "m1",
            "type": "PERSON",
            "surface_text": "Vikram Singh",
            "role_stated": "accused",
            "unit_id": "DOC-001:p001",
            "quote": "Accused: Vikram Singh",
            "attributes": [
                {
                    "name": "age",
                    "value_text": "32 yrs",
                    "quote": "Age: 32 yrs",
                }
            ],
        }
    ],
    "relationships": [],
    "events": [],
    "notes": ["Sample extraction"],
}


# ---------------------------------------------------------------------------
# OpenAI Adapter Tests
# ---------------------------------------------------------------------------


@pytest.mark.gate2
def test_openai_adapter_successful_extraction() -> None:
    """Verify OpenAI adapter constructs correct request payload and validates response."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.refusal = None
    mock_choice.message.content = json.dumps(SAMPLE_MODEL_RESPONSE, ensure_ascii=False)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    adapter = OpenAiAdapter(
        api_key="sk-test-mock-key",
        model_name="gpt-4o-mini",
        temperature=0.0,
        client=mock_client,
    )

    res = adapter.extract("System instructions", "User document evidence", MODEL_SCHEMA)

    assert res["mentions"][0]["surface_text"] == "Vikram Singh"
    assert mock_client.chat.completions.create.call_count == 1

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["temperature"] == 0.0
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "System instructions"},
        {"role": "user", "content": "User document evidence"},
    ]
    assert call_kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "model_output",
            "strict": True,
            "schema": MODEL_SCHEMA,
        },
    }


@pytest.mark.gate2
def test_openai_adapter_truncation_detection() -> None:
    """Verify OpenAI adapter flags length finish_reason as TruncatedOutputError."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "length"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    with pytest.raises(TruncatedOutputError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_openai_adapter_refusal_detection() -> None:
    """Verify OpenAI adapter flags content filter finish_reason as RefusalError."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "content_filter"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    with pytest.raises(RefusalError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_openai_adapter_invalid_json_handling() -> None:
    """Verify OpenAI adapter raises InvalidJsonError on malformed JSON payload."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.refusal = None
    mock_choice.message.content = "Not a JSON document {{{{"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    with pytest.raises(SchemaViolationError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_openai_adapter_schema_violation_handling() -> None:
    """Verify OpenAI adapter raises SchemaViolationError when response violates contract schema."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.refusal = None
    mock_choice.message.content = json.dumps({"unknown_field": True})
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    with pytest.raises(SchemaViolationError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


# ---------------------------------------------------------------------------
# Gemini Adapter Tests
# ---------------------------------------------------------------------------


@pytest.mark.gate2
def test_convert_schema_for_gemini() -> None:
    """Verify schema conversion converts ['string', 'null'] to string + nullable."""
    raw_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "role": {"type": ["string", "null"], "enum": ["accused", "witness", None]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "detail": {"type": ["string", "null"]},
                    },
                },
            },
        },
    }

    converted = convert_schema_for_gemini(raw_schema)
    assert converted["properties"]["role"]["type"] == "string"
    assert converted["properties"]["role"]["nullable"] is True
    assert None not in converted["properties"]["role"]["enum"]
    assert converted["properties"]["items"]["items"]["properties"]["detail"]["type"] == "string"
    assert converted["properties"]["items"]["items"]["properties"]["detail"]["nullable"] is True


@pytest.mark.gate2
def test_gemini_adapter_successful_extraction() -> None:
    """Verify Gemini adapter constructs correct config and validates response."""
    mock_client = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "STOP"
    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = json.dumps(SAMPLE_MODEL_RESPONSE, ensure_ascii=False)
    mock_client.models.generate_content.return_value = mock_response

    adapter = GeminiAdapter(
        api_key="gemini-mock-key",
        model_name="gemini-2.0-flash",
        temperature=0.0,
        client=mock_client,
    )

    res = adapter.extract("System instructions", "User document evidence", MODEL_SCHEMA)

    assert res["mentions"][0]["surface_text"] == "Vikram Singh"
    assert mock_client.models.generate_content.call_count == 1

    call_kwargs = mock_client.models.generate_content.call_args[1]
    assert call_kwargs["model"] == "gemini-2.0-flash"
    assert call_kwargs["contents"] == "User document evidence"
    cfg = call_kwargs["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.system_instruction == "System instructions"
    assert cfg.temperature == 0.0


@pytest.mark.gate2
def test_gemini_adapter_truncation_detection() -> None:
    """Verify Gemini adapter flags MAX_TOKENS finish_reason as TruncatedOutputError."""
    mock_client = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.finish_reason = "MAX_TOKENS"
    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    adapter = GeminiAdapter(api_key="gemini-test", client=mock_client, max_attempts=1)
    with pytest.raises(TruncatedOutputError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_openai_adapter_rate_limit_mapping() -> None:
    """Verify OpenAI 429 error is mapped to RateLimitError with retry-after header."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.headers = {"retry-after": "12.0"}
    mock_client.chat.completions.create.side_effect = openai.RateLimitError(
        message="Rate limit hit",
        response=mock_resp,
        body=None,
    )

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    # Direct _call_raw tests the immediate error classification
    with pytest.raises(RateLimitError) as exc_info:
        adapter._call_raw("sys", "user", MODEL_SCHEMA)
    assert exc_info.value.retry_after == 12.0

    # extract() with retries exhausted raises RetryExhaustedError
    with pytest.raises(RetryExhaustedError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_openai_adapter_auth_error_mapping() -> None:
    """Verify OpenAI 401 error is mapped to AuthError without leaking secrets."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
        message="Invalid key: sk-secret-12345",
        response=MagicMock(),
        body=None,
    )

    adapter = OpenAiAdapter(api_key="sk-secret-12345", client=mock_client, max_attempts=1)
    with pytest.raises(AuthError) as exc_info:
        adapter.extract("sys", "user", MODEL_SCHEMA)
    assert "sk-secret-12345" not in str(exc_info.value)
    assert "401" in str(exc_info.value)


@pytest.mark.gate2
def test_openai_adapter_server_error_mapping() -> None:
    """Verify OpenAI 500 error is mapped to ServerError and RetryExhaustedError on extract."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = openai.InternalServerError(
        message="Internal server error",
        response=MagicMock(),
        body=None,
    )

    adapter = OpenAiAdapter(api_key="sk-test", client=mock_client, max_attempts=1)
    with pytest.raises(ServerError):
        adapter._call_raw("sys", "user", MODEL_SCHEMA)

    with pytest.raises(RetryExhaustedError):
        adapter.extract("sys", "user", MODEL_SCHEMA)


@pytest.mark.gate2
def test_gemini_adapter_error_mappings() -> None:
    """Verify Gemini API errors are mapped to categorized exceptions without leaking secrets."""
    # 401 Auth error
    mock_client_auth = MagicMock()
    mock_client_auth.models.generate_content.side_effect = genai_errors.ClientError(
        401, {"message": "Invalid API Key gemini-secret-999"}
    )
    adapter_auth = GeminiAdapter(api_key="gemini-secret-999", client=mock_client_auth, max_attempts=1)
    with pytest.raises(AuthError) as exc_info:
        adapter_auth.extract("sys", "user", MODEL_SCHEMA)
    assert "gemini-secret-999" not in str(exc_info.value)

    # 429 Rate limit
    mock_client_rl = MagicMock()
    mock_client_rl.models.generate_content.side_effect = genai_errors.ClientError(429, {"message": "Quota exceeded"})
    adapter_rl = GeminiAdapter(api_key="gemini-test", client=mock_client_rl, max_attempts=1)
    with pytest.raises(RateLimitError):
        adapter_rl._call_raw("sys", "user", MODEL_SCHEMA)
    with pytest.raises(RetryExhaustedError):
        adapter_rl.extract("sys", "user", MODEL_SCHEMA)

    # 500 Server error
    mock_client_500 = MagicMock()
    mock_client_500.models.generate_content.side_effect = genai_errors.ServerError(500, {"message": "Internal error"})
    adapter_500 = GeminiAdapter(api_key="gemini-test", client=mock_client_500, max_attempts=1)
    with pytest.raises(ServerError):
        adapter_500._call_raw("sys", "user", MODEL_SCHEMA)
    with pytest.raises(RetryExhaustedError):
        adapter_500.extract("sys", "user", MODEL_SCHEMA)
