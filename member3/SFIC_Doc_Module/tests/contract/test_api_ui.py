"""Contract tests for the development/testing web UI (atlas.api.ui).

Verifies:
- GET / serves the single-page HTML UI.
- GET /ui/config exposes providers and schema enum values (nothing hardcoded client-side).
- The mock-provider honesty banner is surfaced when provider == "mock".
- POST /ui/run runs the pipeline synchronously on an uploaded file and returns
  state, entities, relationships, events, and a graph payload.
- GET /ui/runs/{case_id}/{run_id}/{artifact} downloads a run artifact as a file
  attachment, with an allow-list and path containment checks.
- Invalid input (bad case_id, no files) is rejected with 400.

All tests marked with @pytest.mark.gate4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from atlas.api.app import app
from atlas.api.ui import available_providers
from atlas.config import AtlasSettings, get_settings
from atlas.ingest.synthetic_guard import register_synthetic_files

pytestmark = pytest.mark.gate4


@pytest.fixture
def mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Set up isolated tmp directories for test data and outputs."""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    monkeypatch.setattr(settings, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    # Hermetic: ignore the operator's provider allow-list from the environment.
    monkeypatch.setattr(settings, "LLM_PROVIDERS_ENABLED", "")

    return {"data_dir": data_dir, "output_dir": output_dir}


@pytest.fixture
def client(mock_env: dict[str, Any]) -> TestClient:
    return TestClient(app)


def test_ui_page_serves_html(client: TestClient):
    """GET / returns the single-page HTML UI."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert "<html" in body.lower()
    assert "ui/run" in body


def test_ui_config_lists_providers_and_enums(client: TestClient):
    """GET /ui/config exposes providers and schema enum values."""
    resp = client.get("/ui/config")
    assert resp.status_code == 200
    data = resp.json()

    assert "mock" in data["providers"]
    assert data["active_provider"] == "mock"
    assert data["is_mock"] is True
    assert data["mock_banner"] == "SCRIPTED MOCK PROVIDER: not live extraction"
    assert data["state"] == "available"
    assert len(data["entity_types"]) > 0
    assert "PERSON" in data["entity_types"]
    assert len(data["relationship_types"]) > 0


def test_ui_run_mock_returns_entities_and_graph(client: TestClient, mock_env: dict[str, Any]):
    """POST /ui/run extracts entities and connections and returns a graph payload."""
    file_bytes = b"Synthetic complaint text mentioning a person and a phone number."

    resp = client.post(
        "/ui/run",
        data={"case_id": "CASE-UI-001", "provider": "mock"},
        files={"files": ("ui_unique_sample.txt", file_bytes, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Required top-level keys.
    for key in (
        "state",
        "case_id",
        "run_id",
        "provider",
        "is_mock",
        "mock_banner",
        "documents",
        "mentions",
        "relationships",
        "events",
        "review_items",
        "rejections",
        "warnings",
        "graph",
    ):
        assert key in data, key

    assert data["case_id"] == "CASE-UI-001"
    assert data["state"] in {"completed", "completed_with_warnings"}
    assert isinstance(data["mentions"], list)
    assert isinstance(data["relationships"], list)
    assert isinstance(data["graph"], dict)
    assert data["graph"]["case_id"] == "CASE-UI-001"
    assert "nodes" in data["graph"]
    assert "edges" in data["graph"]


def test_ui_run_mock_banner_displayed(client: TestClient, mock_env: dict[str, Any]):
    """The mock honesty banner is present for a mock-provider run."""
    resp = client.post(
        "/ui/run",
        data={"case_id": "CASE-UI-002", "provider": "mock"},
        files={"files": ("ui_unique_sample2.txt", b"Another synthetic note with a name.", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["is_mock"] is True
    assert data["mock_banner"] == "SCRIPTED MOCK PROVIDER: not live extraction"


def test_ui_config_lists_downloadable_artifacts(client: TestClient):
    """GET /ui/config advertises the artifact names the download route accepts."""
    data = client.get("/ui/config").json()
    assert "result.json" in data["artifacts"]
    assert "review_queue.json" in data["artifacts"]


def test_ui_download_result_json(client: TestClient, mock_env: dict[str, Any]):
    """A completed run's result.json is downloadable as a JSON attachment."""
    run = client.post(
        "/ui/run",
        data={"case_id": "CASE-UI-DL", "provider": "mock"},
        files={"files": ("ui_download_sample.txt", b"Synthetic note for download.", "text/plain")},
    )
    assert run.status_code == 200, run.text
    data = run.json()

    resp = client.get(f"/ui/runs/{data['case_id']}/{data['run_id']}/result.json")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json")
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "result.json" in disposition

    payload = resp.json()
    assert payload["case_id"] == data["case_id"]
    assert payload["run"]["run_id"] == data["run_id"]


def test_ui_download_rejects_unknown_artifact(client: TestClient, mock_env: dict[str, Any]):
    """Only allow-listed artifact names are served."""
    resp = client.get("/ui/runs/CASE-UI-DL/RUN-20260101T000000Z-abcdef/.env")
    assert resp.status_code == 404


def test_ui_download_rejects_invalid_case_and_run_ids(client: TestClient, mock_env: dict[str, Any]):
    """A malformed case id or run id is refused before the filesystem is touched."""
    assert client.get("/ui/runs/..%2Fetc/RUN-20260101T000000Z-abcdef/result.json").status_code in {400, 404}
    assert client.get("/ui/runs/CASE-UI-DL/not-a-run-id/result.json").status_code == 400


def test_ui_download_missing_run_is_404(client: TestClient, mock_env: dict[str, Any]):
    """A well-formed but nonexistent run returns 404 rather than an empty file."""
    resp = client.get("/ui/runs/CASE-UI-NONE/RUN-20260101T000000Z-abcdef/result.json")
    assert resp.status_code == 404


def test_ui_run_rejects_invalid_case_id(client: TestClient, mock_env: dict[str, Any]):
    """A case_id with path-traversal characters is rejected with 400."""
    resp = client.post(
        "/ui/run",
        data={"case_id": "../etc/passwd", "provider": "mock"},
        files={"files": ("sample.txt", b"text", "text/plain")},
    )
    assert resp.status_code == 400


def test_ui_run_rejects_missing_files(client: TestClient, mock_env: dict[str, Any]):
    """A run with no files is rejected (422 validation or 400)."""
    resp = client.post(
        "/ui/run",
        data={"case_id": "CASE-UI-003", "provider": "mock"},
    )
    assert resp.status_code in {400, 422}


def test_ui_run_rejects_empty_upload(client: TestClient, mock_env: dict[str, Any]):
    """A zero-byte upload is skipped rather than silently accepted."""
    resp = client.post(
        "/ui/run",
        data={"case_id": "CASE-UI-004", "provider": "mock"},
        files={"files": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
    assert "No usable files" in resp.json()["detail"]


def test_available_providers_respects_allow_list() -> None:
    """LLM_PROVIDERS_ENABLED narrows the UI provider list; the active provider always survives."""
    only_groq = AtlasSettings(
        LLM_PROVIDER="groq",
        LLM_MODEL="test-model",
        LLM_PROVIDERS_ENABLED="groq",
        GROQ_API_KEY="test-groq-key",
        OPENAI_API_KEY=None,
        GEMINI_API_KEY=None,
    )
    assert available_providers(only_groq) == ["groq"]

    # An empty allow-list offers every provider with configured credentials.
    open_list = AtlasSettings(
        LLM_PROVIDER="mock",
        LLM_PROVIDERS_ENABLED="",
        GROQ_API_KEY="test-groq-key",
        OPENAI_API_KEY=None,
        GEMINI_API_KEY=None,
    )
    assert available_providers(open_list) == ["mock", "groq"]

    # The configured provider is never hidden, even if the allow-list omits it.
    mismatched = AtlasSettings(
        LLM_PROVIDER="mock",
        LLM_PROVIDERS_ENABLED="gemini",
        GROQ_API_KEY=None,
        OPENAI_API_KEY=None,
        GEMINI_API_KEY=None,
    )
    assert available_providers(mismatched)[0] == "mock"


def test_ui_config_respects_allow_list(client: TestClient, mock_env: dict[str, Any]):
    """The dev UI only offers providers the operator enabled."""
    settings = get_settings()
    settings.LLM_PROVIDERS_ENABLED = "groq"
    settings.LLM_PROVIDER = "groq"
    settings.GROQ_API_KEY = settings.GROQ_API_KEY or None
    try:
        resp = client.get("/ui/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["providers"] == ["groq"]
        assert data["active_provider"] == "groq"
    finally:
        settings.LLM_PROVIDERS_ENABLED = ""
        settings.LLM_PROVIDER = "mock"


def test_ui_run_rejects_disabled_provider(client: TestClient, mock_env: dict[str, Any]):
    """A provider outside the allow-list is refused with 400 before any work happens."""
    settings = get_settings()
    settings.LLM_PROVIDERS_ENABLED = "groq"
    try:
        resp = client.post(
            "/ui/run",
            data={"case_id": "CASE-UI-005", "provider": "mock"},
            files={"files": ("sample.txt", b"text", "text/plain")},
        )
    finally:
        settings.LLM_PROVIDERS_ENABLED = ""
    assert resp.status_code == 400
    assert "not enabled" in resp.json()["detail"]


def test_ui_run_missing_model_is_reported_clearly(client: TestClient, mock_env: dict[str, Any]):
    """A live provider without LLM_MODEL fails with an actionable 400 (model names are never defaulted)."""
    settings = get_settings()
    settings.LLM_PROVIDERS_ENABLED = "groq"
    original_model = settings.LLM_MODEL
    settings.LLM_MODEL = ""
    try:
        resp = client.post(
            "/ui/run",
            data={"case_id": "CASE-UI-006", "provider": "groq"},
            files={"files": ("note.txt", b"Synthetic note about a person.", "text/plain")},
        )
    finally:
        settings.LLM_MODEL = original_model
        settings.LLM_PROVIDERS_ENABLED = ""
    assert resp.status_code == 400
    assert "LLM_MODEL" in resp.json()["detail"]


def test_ui_run_reports_synthetic_guard_rejection(client: TestClient, mock_env: dict[str, Any]):
    """An unregistered file under a live provider is rejected with an explanatory state_note."""
    settings = get_settings()
    settings.LLM_PROVIDERS_ENABLED = "groq"
    settings.LLM_PROVIDER = "groq"
    original_model = settings.LLM_MODEL
    settings.LLM_MODEL = original_model or "test-model"
    try:
        resp = client.post(
            "/ui/run",
            data={"case_id": "CASE-UI-007", "provider": "groq"},
            files={"files": ("unregistered_sample.txt", b"Synthetic note with a name.", "text/plain")},
        )
    finally:
        settings.LLM_MODEL = original_model
        settings.LLM_PROVIDER = "mock"
        settings.LLM_PROVIDERS_ENABLED = ""
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "rejected_input"
    assert data["mentions"] == []
    assert data["state_note"] and "synthetic-data guard" in data["state_note"]


def test_register_synthetic_files_adds_hashes(tmp_path: Path) -> None:
    """Registering a file records its SHA-256 in the manifest (human attestation path)."""
    import hashlib
    import json

    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"synthetic content")
    manifest = tmp_path / "data" / "synthetic_manifest.json"

    assert register_synthetic_files([sample, tmp_path / "missing.txt"], manifest) == 1

    data = json.loads(manifest.read_text(encoding="utf-8"))
    digest = hashlib.sha256(b"synthetic content").hexdigest()
    assert data[digest] == "sample.txt"

    # Registering again is idempotent (same hash key).
    assert register_synthetic_files([sample], manifest) == 1
    assert len(json.loads(manifest.read_text(encoding="utf-8"))) == 1
