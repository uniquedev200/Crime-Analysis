"""Gate 0 contract and identifier tests."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from atlas.contracts.enums import (
    Assertion,
    DocumentStatus,
    EntityType,
    EventType,
    JobState,
    OcrLevel,
    Origin,
    QuoteStatus,
    RejectionKind,
    RelType,
    ReviewActionType,
    ReviewKind,
    StatedRole,
    SuggestionStatus,
    UnitKind,
)
from atlas.contracts.export_schemas import export_schemas
from atlas.contracts.ids import (
    make_doc_id,
    make_idempotency_key,
    make_mention_id,
    make_run_id,
    safe_filename,
    validate_case_id,
)
from atlas.contracts.model_schema import MODEL_SCHEMA, lint_provider_schema
from atlas.contracts.records import (
    Aggregate,
    CaseResult,
    DocumentRecord,
    Event,
    EventTime,
    Mention,
    OcrInfo,
    Rejection,
    Relationship,
    ResolutionSuggestion,
    ReviewAction,
    ReviewItem,
    RunMeta,
    SourceRef,
)


@pytest.mark.gate0
def test_case_id_valid() -> None:
    valid_ids = ["CASE-001", "case_123", "CASE-A-99", "c", "1", "a" * 64]
    for cid in valid_ids:
        assert validate_case_id(cid) == cid


@pytest.mark.gate0
def test_case_id_rejects_traversal() -> None:
    invalid_ids = ["../etc", "a/b", "a\\b", "", "..", ".", "/root", "case/1", "case\\1"]
    for bad in invalid_ids:
        with pytest.raises(ValueError, match="Invalid case_id"):
            validate_case_id(bad)


@pytest.mark.gate0
def test_case_id_rejects_too_long() -> None:
    too_long = "a" * 65
    with pytest.raises(ValueError, match="Invalid case_id"):
        validate_case_id(too_long)


@pytest.mark.gate0
def test_doc_id_format() -> None:
    raw_bytes = b"sample test content for hashing"
    sha = hashlib.sha256(raw_bytes).hexdigest()
    doc_id = make_doc_id(sha)
    assert doc_id == f"DOC-{sha[:12]}"
    assert doc_id.startswith("DOC-")
    assert len(doc_id) == 16  # 'DOC-' (4) + 12 chars = 16


@pytest.mark.gate0
@given(
    doc_id=st.text(min_size=1, max_size=20),
    unit_id=st.text(min_size=1, max_size=20),
    type_str=st.text(min_size=1, max_size=20),
    val=st.text(min_size=1, max_size=20),
    idx=st.integers(min_value=0, max_value=1000),
)
def test_mention_id_deterministic(
    doc_id: str,
    unit_id: str,
    type_str: str,
    val: str,
    idx: int,
) -> None:
    id1 = make_mention_id(doc_id, unit_id, type_str, val, idx)
    id2 = make_mention_id(doc_id, unit_id, type_str, val, idx)
    assert id1 == id2
    assert id1.startswith("M-")
    assert len(id1) == 14  # 'M-' (2) + 12 hex = 14


@pytest.mark.gate0
def test_run_id_format() -> None:
    run_id = make_run_id()
    pattern = r"^RUN-\d{8}T\d{6}Z-[0-9a-f]{6}$"
    assert re.match(pattern, run_id), f"run_id {run_id} did not match {pattern}"
    assert ":" not in run_id
    assert "+" not in run_id


@pytest.mark.gate0
def test_safe_filename() -> None:
    raw = "case:A+doc?name*file/one\\two|three.json"
    cleaned = safe_filename(raw)
    assert ":" not in cleaned
    assert "+" not in cleaned
    assert "?" not in cleaned
    assert "*" not in cleaned
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert "|" not in cleaned
    assert cleaned == "case_A_doc_name_file_one_two_three.json"


@pytest.mark.gate0
def test_records_round_trip() -> None:
    source = SourceRef(
        doc_id="DOC-123456789012",
        file_name="fir_001.pdf",
        file_sha256="a" * 64,
        unit_id="DOC-123456789012:p001",
        unit_kind=UnitKind.PAGE,
        page=1,
        text_origin=Origin.PDF_TEXT,
        quote="Accused Rajesh entered the premises",
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )

    ocr = OcrInfo(
        level=OcrLevel.WORD,
        min=85.0,
        mean=94.5,
        engine="tesseract",
        langs=["eng"],
    )

    mention = Mention(
        mention_id="M-123456789012",
        case_id="CASE-001",
        doc_id="DOC-123456789012",
        type=EntityType.PERSON,
        surface_text="Rajesh",
        stated_role=StatedRole.ACCUSED,
        origin=Origin.PDF_TEXT,
        source=source,
    )

    rel = Relationship(
        rel_id="R-123456789012",
        case_id="CASE-001",
        type=RelType.USES_PHONE,
        subject_mention_id="M-123456789012",
        object_mention_id="M-987654321098",
        assertion=Assertion.STATED,
        origin=Origin.PDF_TEXT,
        source=source,
    )

    event = Event(
        event_id="E-123456789012",
        case_id="CASE-001",
        type=EventType.INCIDENT,
        description="Theft reported at residence",
        time=EventTime(original_text="12/10/2026"),
        origin=Origin.PDF_TEXT,
        source=source,
    )

    agg = Aggregate(
        aggregate_id="AGG-123456789012",
        case_id="CASE-001",
        type=RelType.CALLED,
        subject_mention_id="M-123456789012",
        object_mention_id="M-987654321098",
        count=12,
        total_duration_s=360,
    )

    rev = ReviewItem(
        review_id="REV-123456789012",
        case_id="CASE-001",
        kind=ReviewKind.LOW_TRUST_IDENTIFIER,
        target_ids=["M-123456789012"],
        detail="Low OCR confidence score on phone number",
    )

    rej = Rejection(
        rejection_id="REJ-123456789012",
        case_id="CASE-001",
        doc_id="DOC-123456789012",
        kind=RejectionKind.QUOTE_NOT_FOUND,
        reason="Extracted quote not found in page text",
        model_item_excerpt="Rajesh theft quote",
    )

    doc_rec = DocumentRecord(
        doc_id="DOC-123456789012",
        file_name="fir_001.pdf",
        file_sha256="a" * 64,
        size_bytes=4096,
        detected_type="pdf",
        status=DocumentStatus.PROCESSED,
    )

    run_meta = RunMeta(
        run_id="RUN-20261013T120000Z-abcdef",
        started_at="2026-10-13T12:00:00Z",
        finished_at="2026-10-13T12:00:05Z",
        pipeline_version="1.0.0",
        schema_version="1.0.0",
        prompt_version="extract-v1",
        provider="mock",
        model="mock-v1",
        temperature=0.0,
        ocr_engine="tesseract",
        ocr_version="5.3.0",
        ocr_langs=["eng"],
        normalization_version="1.0.0",
        resolver_version="1.0.0",
        idempotency_key="0" * 64,
    )

    case_result = CaseResult(
        schema_version="1.0.0",
        case_id="CASE-001",
        run=run_meta,
        state=JobState.COMPLETED,
        documents=[doc_rec],
        mentions=[mention],
        relationships=[rel],
        events=[event],
        aggregates=[agg],
        review_items=[rev],
        rejections=[rej],
        warnings=[],
    )

    sug = ResolutionSuggestion(
        suggestion_id="SUG-123456789012",
        case_id="CASE-001",
        mention_id="M-123456789012",
        candidate_entity_id="PERSON:CASE-002:c1",
        candidate_case_id="CASE-002",
        status=SuggestionStatus.CANDIDATE,
        heuristic_rank=0.92,
        explanation="Exact phone match across cases",
    )

    action = ReviewAction(
        action_id="ACT-1234567890ab",
        type=ReviewActionType.APPROVE_MATCH,
        actor="analyst_1",
        at="2026-10-13T12:00:00Z",
        reason="Phone number matches external record",
        target_ids=["SUG-123456789012"],
        prev_hash="0" * 64,
        entry_hash="1" * 64,
        case_id="CASE-001",
    )

    records = [
        source,
        ocr,
        mention,
        rel,
        event,
        agg,
        rev,
        rej,
        doc_rec,
        run_meta,
        case_result,
        sug,
        action,
    ]

    for model_inst in records:
        dumped_json = model_inst.model_dump_json()
        reloaded = type(model_inst).model_validate_json(dumped_json)
        assert reloaded == model_inst, f"Round-trip failed for {type(model_inst).__name__}"


@pytest.mark.gate0
def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        SourceRef(
            doc_id="DOC-123456789012",
            file_name="fir_001.pdf",
            file_sha256="a" * 64,
            unit_id="DOC-123456789012:p001",
            unit_kind=UnitKind.PAGE,
            text_origin=Origin.PDF_TEXT,
            quote="Accused Rajesh entered the premises",
            quote_status=QuoteStatus.VERIFIED,
            occurrence_count=1,
            unauthorized_field="unexpected",  # extra="forbid"
        )


@pytest.mark.gate0
def test_model_schema_lint() -> None:
    errors = lint_provider_schema(MODEL_SCHEMA)
    assert not errors, f"MODEL_SCHEMA failed provider lint: {errors}"


@pytest.mark.gate0
def test_export_schemas(tmp_path: Path) -> None:
    out_dir = tmp_path / "contracts"
    exported = export_schemas(out_dir)
    assert len(exported) > 0

    for name, schema_path in exported.items():
        assert schema_path.exists(), f"Schema file {schema_path} does not exist"
        with open(schema_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), f"Schema {name} is not a valid JSON dict"
        assert "properties" in data or "type" in data, f"Schema {name} lacks basic JSON Schema structure"


@pytest.mark.gate0
def test_utf8_round_trip() -> None:
    # Devanagari and Tamil text
    hindi_name = "रमेश कुमार (अभियुक्त)"
    tamil_location = "சென்னை அண்ணா சாலை"

    source = SourceRef(
        doc_id="DOC-123456789012",
        file_name="fir_hindi.pdf",
        file_sha256="a" * 64,
        unit_id="DOC-123456789012:p001",
        unit_kind=UnitKind.PAGE,
        text_origin=Origin.OCR,
        quote=f"आरोपी {hindi_name} उपस्थित था",
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )

    mention = Mention(
        mention_id="M-123456789012",
        case_id="CASE-001",
        doc_id="DOC-123456789012",
        type=EntityType.PERSON,
        surface_text=hindi_name,
        stated_role=StatedRole.ACCUSED,
        origin=Origin.OCR,
        source=source,
    )

    json_str = mention.model_dump_json()
    # Ensure UTF-8 strings do not get corrupted
    reloaded = Mention.model_validate_json(json_str)
    assert reloaded.surface_text == hindi_name
    assert reloaded.source.quote == f"आरोपी {hindi_name} उपस्थित था"

    # Also test Tamil in event description
    event = Event(
        event_id="E-123456789012",
        case_id="CASE-001",
        type=EventType.INCIDENT,
        description=f"சம்பவம் நடந்த இடம்: {tamil_location}",
        origin=Origin.PDF_TEXT,
        source=source,
    )
    event_json = event.model_dump_json()
    reloaded_event = Event.model_validate_json(event_json)
    assert reloaded_event.description == f"சம்பவம் நடந்த இடம்: {tamil_location}"


@pytest.mark.gate0
def test_idempotency_key_stable() -> None:
    args = {
        "file_sha256": "abcdef1234567890" * 4,
        "pipeline_version": "1.0.0",
        "ocr_engine": "tesseract",
        "ocr_version": "5.3.0",
        "ocr_langs": ["eng", "hin"],
        "provider": "mock",
        "model": "mock-v1",
        "prompt_version": "extract-v1",
        "schema_version": "1.0.0",
        "normalization_version": "1.0.0",
    }

    key1 = make_idempotency_key(**args)
    key2 = make_idempotency_key(**args)
    assert key1 == key2
    assert len(key1) == 64

    # Changing any argument produces a different hash
    args_altered = dict(args)
    args_altered["file_sha256"] = "1111111111111111" * 4
    key3 = make_idempotency_key(**args_altered)
    assert key1 != key3
