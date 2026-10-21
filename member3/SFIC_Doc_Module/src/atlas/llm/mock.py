"""Mock and Faulty LLM providers for test simulation and offline development.

- MockProvider: Returns pre-scripted responses from fixtures for deterministic testing.
- FaultyProvider: Simulates provider failures (429, 5xx, timeout, truncation, etc.)
  to test retry and recovery policies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from atlas.contracts.model_schema import validate_model_output
from atlas.errors import ProviderError, SchemaViolationError
from atlas.llm.retry import (
    AuthError,
    ConnectionError,
    InvalidJsonError,
    RateLimitError,
    RefusalError,
    ServerError,
    TimeoutError,
    TruncatedOutputError,
)
from atlas.ports.llm import LlmClientPort

DEFAULT_FIXTURES_DIR = Path("tests/fixtures/model_responses")


class MockProvider(LlmClientPort):
    """Scripted LLM provider reading recorded responses from fixtures."""

    def __init__(
        self,
        fixtures_dir: Path | str = DEFAULT_FIXTURES_DIR,
        provider_name: str = "mock",
        model_name: str = "scripted",
    ) -> None:
        self._fixtures_dir = Path(fixtures_dir).resolve()
        self._provider_name = provider_name
        self._model_name = model_name
        self.captured_prompts: list[dict[str, Any]] = []
        self._doc_call_counts: dict[str, int] = {}
        self._custom_responses: dict[str, dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        """Name of the provider ('mock')."""
        return self._provider_name

    @property
    def model_name(self) -> str:
        """Name of the active model ('scripted')."""
        return self._model_name

    def register_response(self, doc_key: str, chunk: int, response: dict[str, Any]) -> None:
        """Register a scripted response in-memory for testing."""
        key = f"{doc_key}_{chunk}"
        self._custom_responses[key] = response

    def _find_fixture_response(self, doc_candidates: list[str], chunk_idx: int) -> dict[str, Any] | None:
        """Search for a matching fixture response across candidate stems and directories."""
        # 1. In-memory registered responses
        for cand in doc_candidates:
            key = f"{cand}_{chunk_idx}"
            if key in self._custom_responses:
                return self._custom_responses[key]

        if not self._fixtures_dir.exists():
            return None

        # 2. Check direct file variations
        for cand in doc_candidates:
            file_names = [
                f"{cand}_{chunk_idx}.json",
                f"{cand}.pdf_{chunk_idx}.json",
                f"{cand}.txt_{chunk_idx}.json",
                f"{cand}.csv_{chunk_idx}.json",
                f"{cand}.xlsx_{chunk_idx}.json",
            ]
            for fn in file_names:
                fpath = self._fixtures_dir / fn
                if fpath.is_file():
                    raw = json.loads(fpath.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        return raw

        # 3. Scan JSON fixtures to match doc_id / unit_id in the content
        for cand in doc_candidates:
            for p in self._fixtures_dir.glob(f"*_{chunk_idx}.json"):
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        raw_str = json.dumps(raw, ensure_ascii=False)
                        if cand in raw_str:
                            return raw
                except Exception:
                    continue

        return None

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform scripted extraction returning verified model output."""
        self.captured_prompts.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
            }
        )

        # Extract unit_ids from user prompt
        unit_matches = re.findall(r"\[UNIT\s+([^\]]+)\]", user)
        doc_candidates: list[str] = []
        chunk_idx = 0

        if unit_matches:
            first_unit = unit_matches[0].strip()
            # If unit_id has page marker, determine chunk index
            p_match = re.search(r":p(\d+)", first_unit)
            if p_match:
                page_num = int(p_match.group(1))
                # Page 1 is chunk 0, page 2 is chunk 1, etc.
                chunk_idx = max(0, page_num - 1)

            # Document ID / stem from unit_id
            doc_id = first_unit.split(":")[0]
            doc_candidates.append(doc_id)

            # Also check for known document names mentioned in user prompt
            for known in ("FIR_A", "FIR_B", "IO_REPORT_A", "SURVEILLANCE_A", "BANK_A", "CDR_A", "CDR_B"):
                if known in user:
                    doc_candidates.append(known)

            # Track call counts per document
            current_count = self._doc_call_counts.get(doc_id, 0)
            self._doc_call_counts[doc_id] = current_count + 1
        else:
            doc_candidates.append("default")

        # Try chunk_idx derived from page, or fallback to sequential call count
        resp = self._find_fixture_response(doc_candidates, chunk_idx)
        if resp is None and unit_matches:
            doc_id = unit_matches[0].split(":")[0]
            alt_chunk = self._doc_call_counts.get(doc_id, 1) - 1
            if alt_chunk != chunk_idx:
                resp = self._find_fixture_response(doc_candidates, alt_chunk)

        # Fallback to empty valid model output if no fixture is found
        if resp is None:
            resp = {
                "mentions": [],
                "relationships": [],
                "events": [],
                "notes": ["SCRIPTED MOCK PROVIDER: not live extraction"],
            }

        return validate_model_output(resp)


class FaultyProvider(LlmClientPort):
    """Simulated LLM provider that reproduces failure scenarios for testing."""

    def __init__(
        self,
        failure_mode: str = "rate_limit",
        fail_times: int = 1,
        retry_after: float | None = None,
        success_response: dict[str, Any] | None = None,
        provider_name: str = "faulty",
        model_name: str = "faulty-sim",
    ) -> None:
        self.failure_mode = failure_mode.lower().strip()
        self.fail_times = fail_times
        self.retry_after = retry_after
        self._success_response = success_response or {
            "mentions": [],
            "relationships": [],
            "events": [],
            "notes": ["FaultyProvider recovered successfully"],
        }
        self._provider_name = provider_name
        self._model_name = model_name
        self.call_count: int = 0
        self.captured_prompts: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform extraction, simulating the configured failure if within fail_times."""
        self.call_count += 1
        self.captured_prompts.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
            }
        )

        should_fail = (self.fail_times < 0) or (self.call_count <= self.fail_times)

        if should_fail:
            mode = self.failure_mode
            if mode in ("rate_limit", "429"):
                raise RateLimitError("Rate limit exceeded (429)", retry_after=self.retry_after)
            elif mode in ("server_error", "500", "503"):
                raise ServerError("Internal server error (500)")
            elif mode == "timeout":
                raise TimeoutError("Request timed out")
            elif mode == "connection_error":
                raise ConnectionError("Connection to provider failed")
            elif mode == "truncated":
                raise TruncatedOutputError("Output truncated (length finish)")
            elif mode == "invalid_json":
                raise InvalidJsonError("Non-JSON output returned by provider")
            elif mode == "schema_violation":
                raise SchemaViolationError("Model output violated schema: extra unknown field")
            elif mode in ("refusal", "safety"):
                raise RefusalError("Request blocked by safety filter")
            elif mode in ("auth_error", "401", "403"):
                raise AuthError("Authentication/authorization failed (401/403). Check credentials.")
            else:
                raise ProviderError(f"Simulated unknown failure mode: {mode}")

        return validate_model_output(self._success_response)


__all__ = [
    "FaultyProvider",
    "MockProvider",
]
