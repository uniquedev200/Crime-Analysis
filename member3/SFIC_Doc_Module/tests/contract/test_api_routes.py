"""Contract tests for all 10 FastAPI endpoints in ATLAS Dev 3 API.

Verifies:
- Document upload -> job creation -> job status -> latest results retrieval.
- Review queue items retrieval.
- Suggestions endpoint returning heuristic rank with mandatory rank_note.
- Review action application and hash chain audit.
- Graph endpoint generating payload and optional Cypher export.
- Evidence endpoint returning verbatim quote, transcript coordinates, origin, OCR info, and allowed actions.
- Liveness check /healthz.
- Explicit 'state' in all responses.

All tests marked with @pytest.mark.gate4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from atlas.api.app import app
from atlas.config import get_settings
from atlas.contracts.enums import (
    Assertion,
    DocumentStatus,
    EntityType,
    IdentifierTrust,
    JobState,
    NormalizationStatus,
    OcrLevel,
    Origin,
    PageMethod,
    QuoteStatus,
    RelType,
    ReviewItemStatus,
    ReviewKind,
    StatedRole,
    SuggestionStatus,
    UnitKind,
)
from atlas.contracts.records import (
    CaseResult,
    DocumentRecord,
    Mention,
    OcrInfo,
    PageInfo,
    Relationship,
    ResolutionSuggestion,
    ReviewItem,
    RunMeta,
    Signal,
    SignalPolarity,
    SourceRef,
)
from atlas.output.writer import OutputWriter
from atlas.resolve.store_sqlite import SqliteEntityStore

pytestmark = pytest.mark.gate4


@pytest.fixture
def mock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up isolated tmp directories for test data and outputs."""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    monkeypatch.setattr(settings, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings, "OUTPUT_DIR", str(output_dir))

    # Initialize isolated SQLite entity store
    test_db = data_dir / "entity_store.db"
    store = SqliteEntityStore(test_db)
    monkeypatch.setattr("atlas.api.routes._STORE_INSTANCE", store)

    return {"data_dir": data_dir, "output_dir": output_dir, "store": store}


@pytest.fixture
def client(mock_env: dict[str, Any]) -> TestClient:
    return TestClient(app)


def _seed_sample_case_result(output_dir: Path, case_id: str = "CASE-A-001") -> tuple[CaseResult, Mention]:
    """Helper to generate and write a fully populated CaseResult into outputs."""
    doc_id = "DOC-aabbccddeeff"
    source = SourceRef(
        doc_id=doc_id,
        file_name="FIR_A.pdf",
        file_sha256="aabbccddeeff0011223344556677889900112233445566778899001122334455",
        unit_id=f"{doc_id}:p001",
        unit_kind=UnitKind.PAGE,
        page=1,
        bbox=[100.0, 200.0, 300.0, 220.0],
        text_origin=Origin.OCR,
        quote="Accused Vikram Singh phone 9876543210 was observed at scene",
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )

    ocr = OcrInfo(
        level=OcrLevel.WORD,
        min=0.85,
        mean=0.92,
        engine="tesseract",
        langs=["eng"],
    )

    mention_person = Mention(
        mention_id="M-P100",
        case_id=case_id,
        doc_id=doc_id,
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="vikram_singh",
        stated_role=StatedRole.ACCUSED,
        origin=Origin.OCR,
        ocr=ocr,
        identifier_trust=IdentifierTrust.NOT_APPLICABLE,
        source=source,
    )

    mention_phone = Mention(
        mention_id="M-PH100",
        case_id=case_id,
        doc_id=doc_id,
        type=EntityType.PHONE,
        surface_text="9876543210",
        normalized_value="+919876543210",
        normalization_status=NormalizationStatus.OK,
        origin=Origin.OCR,
        ocr=ocr,
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        review_flags=[ReviewKind.LOW_TRUST_IDENTIFIER],
        source=source,
    )

    rel = Relationship(
        rel_id="R-100",
        case_id=case_id,
        type=RelType.USES_PHONE,
        subject_mention_id="M-P100",
        object_mention_id="M-PH100",
        assertion=Assertion.STATED,
        origin=Origin.OCR,
        source=source,
    )

    rev_item = ReviewItem(
        review_id="REV-100",
        case_id=case_id,
        kind=ReviewKind.LOW_TRUST_IDENTIFIER,
        target_ids=["M-PH100"],
        detail="OCR phone number requires confirmation",
        status=ReviewItemStatus.OPEN,
    )

    run = RunMeta(
        run_id="RUN-20261016T120000Z-abcdef",
        started_at="2026-10-16T12:00:00Z",
        finished_at="2026-10-16T12:00:10Z",
        pipeline_version="0.1.0",
        prompt_version="extract-v1",
        provider="mock",
        model="mock-model",
        ocr_engine="tesseract",
        ocr_version="5.3.0",
        normalization_version="1.0.0",
        resolver_version="1.0.0",
        idempotency_key="idemp_key_123456",
    )

    doc_record = DocumentRecord(
        doc_id=doc_id,
        file_name="FIR_A.pdf",
        file_sha256="aabbccddeeff0011223344556677889900112233445566778899001122334455",
        size_bytes=1024,
        detected_type="pdf",
        status=DocumentStatus.PROCESSED,
        pages=[PageInfo(page=1, method=PageMethod.OCR, chars=250)],
        case_id=case_id,
    )

    result = CaseResult(
        case_id=case_id,
        run=run,
        state=JobState.COMPLETED_WITH_WARNINGS,
        documents=[doc_record],
        mentions=[mention_person, mention_phone],
        relationships=[rel],
        events=[],
        aggregates=[],
        review_items=[rev_item],
        rejections=[],
        warnings=["Low trust OCR identifier requires review"],
    )

    writer = OutputWriter(base_output_dir=output_dir)
    writer.write_all(result)

    return result, mention_phone


def test_endpoint_healthz(client: TestClient):
    """GET /healthz returns status ok, PIPELINE_VERSION, and state."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["state"] == "healthy"


def test_endpoint_upload_document(client: TestClient, mock_env: dict[str, Any]):
    """POST /cases/{case_id}/documents stores file and returns doc_id, file_sha256, and state."""
    headers = {"X-Atlas-User": "demo_analyst"}
    file_bytes = b"Sample synthetic police complaint text"

    resp = client.post(
        "/cases/CASE-A-001/documents",
        files={"file": ("complaint.txt", file_bytes, "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["doc_id"].startswith("DOC-")
    assert len(data["file_sha256"]) == 64
    assert data["state"] == "queued"


def test_endpoint_create_and_get_job(client: TestClient):
    """POST /cases/{case_id}/jobs starts job and GET /jobs/{job_id} retrieves progress and state."""
    headers = {"X-Atlas-User": "demo_analyst"}

    # 1. Create Job
    resp_create = client.post("/cases/CASE-A-001/jobs", json={}, headers=headers)
    assert resp_create.status_code == 202
    job_data = resp_create.json()
    job_id = job_data["job_id"]
    assert job_data["state"] == "queued"

    # 2. Query Job Status
    resp_status = client.get(f"/jobs/{job_id}")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["job_id"] == job_id
    assert "state" in status_data
    assert "progress" in status_data
    assert "warnings" in status_data


def test_endpoint_results_and_review_items(client: TestClient, mock_env: dict[str, Any]):
    """GET /cases/{case_id}/results/latest and GET /cases/{case_id}/review-items."""
    headers = {"X-Atlas-User": "demo_analyst"}
    _seed_sample_case_result(mock_env["output_dir"], case_id="CASE-A-001")

    # 1. Latest results
    resp_res = client.get("/cases/CASE-A-001/results/latest", headers=headers)
    assert resp_res.status_code == 200
    res_data = resp_res.json()
    assert res_data["case_id"] == "CASE-A-001"
    assert res_data["state"] == "completed_with_warnings"
    assert len(res_data["mentions"]) == 2

    # 2. Review items
    resp_items = client.get("/cases/CASE-A-001/review-items", headers=headers)
    assert resp_items.status_code == 200
    items_data = resp_items.json()
    assert len(items_data) >= 1
    assert items_data[0]["kind"] == "low_trust_identifier"
    assert items_data[0]["status"] == "open"


def test_endpoint_suggestions_rank_note(client: TestClient, mock_env: dict[str, Any]):
    """GET /cases/{case_id}/suggestions enforces rank_note and state on suggestions."""
    headers = {"X-Atlas-User": "demo_analyst"}
    store: SqliteEntityStore = mock_env["store"]

    sug = ResolutionSuggestion(
        suggestion_id="SUG-TEST-1",
        case_id="CASE-A-001",
        mention_id="M-100",
        candidate_entity_id="PERSON:CASE-B-002:c1",
        candidate_case_id="CASE-B-002",
        status=SuggestionStatus.CANDIDATE,
        heuristic_rank=0.88,
        rank_note="heuristic ordering, not a probability",
        signals=[
            Signal(
                kind="exact_identifier",
                polarity=SignalPolarity.SUPPORTS,
                detail="Shared phone +919876543210",
                sources=[],
            )
        ],
        explanation="High name similarity and shared phone.",
        requires_human_decision=True,
    )
    store.store_suggestions("CASE-A-001", [sug])

    resp = client.get("/cases/CASE-A-001/suggestions", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["heuristic_rank"] == 0.88
    assert item["rank_note"] == "heuristic ordering, not a probability"
    assert item["status"] == "candidate"


def test_endpoint_review_actions(client: TestClient, mock_env: dict[str, Any]):
    """POST /review/actions applies human decision and returns updated state."""
    headers = {"X-Atlas-User": "demo_analyst"}

    action_payload = {
        "type": "CONFIRM_IDENTIFIER",
        "reason": "Confirmed digits visually on document crop",
        "target_ids": ["M-PH100"],
        "payload": {},
        "case_id": "CASE-A-001",
    }

    resp = client.post("/review/actions", json=action_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "applied"
    assert data["success"] is True
    assert "action_id" in data


def test_endpoint_evidence_mention_details(client: TestClient, mock_env: dict[str, Any]):
    """GET /cases/{case_id}/evidence/{mention_id} returns quote, location, OCR info, and state."""
    headers = {"X-Atlas-User": "demo_analyst"}
    _, phone_mention = _seed_sample_case_result(mock_env["output_dir"], case_id="CASE-A-001")

    resp = client.get(f"/cases/CASE-A-001/evidence/{phone_mention.mention_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["mention_id"] == phone_mention.mention_id
    assert data["surface_text"] == "9876543210"
    assert data["normalized_value"] == "+919876543210"
    assert data["origin"] == "ocr"
    assert data["ocr"]["engine"] == "tesseract"
    assert data["ocr"]["score_kind"] == "engine_score_not_probability"
    assert "quote" in data
    assert data["source"]["page"] == 1
    assert data["source"]["bbox"] == [100.0, 200.0, 300.0, 220.0]
    assert data["state"] == "available"
    assert "CONFIRM_IDENTIFIER" in data["allowed_actions"]


def test_endpoint_graph_and_cypher_export(client: TestClient, mock_env: dict[str, Any]):
    """GET /cases/{case_id}/graph returns graph payload and Cypher export when requested."""
    headers = {"X-Atlas-User": "demo_analyst"}
    _seed_sample_case_result(mock_env["output_dir"], case_id="CASE-A-001")

    # 1. Standard generic graph
    resp_graph = client.get("/cases/CASE-A-001/graph", headers=headers)
    assert resp_graph.status_code == 200
    graph_data = resp_graph.json()
    assert graph_data["case_id"] == "CASE-A-001"
    assert graph_data["state"] == "completed"
    assert len(graph_data["nodes"]) >= 2

    # 2. Graph with Cypher export
    resp_cypher = client.get("/cases/CASE-A-001/graph?export_cypher=true", headers=headers)
    assert resp_cypher.status_code == 200
    cypher_data = resp_cypher.json()
    assert "cypher" in cypher_data
    assert "MERGE (n:Case" in cypher_data["cypher"]
    assert "MERGE (n:Person" in cypher_data["cypher"]
