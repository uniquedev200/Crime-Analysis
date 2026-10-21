"""Contract unit and schema tests for Wave 0 / Gate 0."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.contracts.enums import (
    Assertion,
    AttrName,
    DocumentStatus,
    EntityType,
    EventType,
    IdentifierTrust,
    JobState,
    NormalizationStatus,
    OcrLevel,
    Origin,
    PageMethod,
    QuoteStatus,
    RejectionKind,
    RelType,
    ReviewActionType,
    ReviewItemStatus,
    ReviewKind,
    SheetState,
    SignalPolarity,
    StatedRole,
    SuggestionStatus,
    TimeAmbiguity,
    UnitKind,
)
from atlas.contracts.export_schemas import export_schemas
from atlas.contracts.ids import (
    make_action_id,
    make_aggregate_id,
    make_doc_id,
    make_event_id,
    make_idempotency_key,
    make_mention_id,
    make_rejection_id,
    make_rel_id,
    make_review_id,
    make_run_id,
    make_suggestion_id,
    make_unit_id_json,
    make_unit_id_line,
    make_unit_id_page,
    make_unit_id_row,
    make_unit_id_text_line,
    safe_filename,
    validate_case_id,
)
from atlas.contracts.model_schema import (
    MODEL_SCHEMA,
    lint_provider_schema,
    validate_model_output,
)
from atlas.contracts.records import (
    Aggregate,
    CaseResult,
    DocumentRecord,
    Event,
    EventAmount,
    EventParticipant,
    EventTime,
    Mention,
    MentionAttribute,
    OcrInfo,
    PageInfo,
    Rejection,
    Relationship,
    ResolutionSuggestion,
    ReviewAction,
    ReviewItem,
    RunMeta,
    SheetInfo,
    Signal,
    SourceRef,
    ValidationCheck,
)

pytestmark = pytest.mark.gate0


def test_case_id_validation_valid():
    """Valid case IDs matching ^[A-Za-z0-9_-]{1,64}$ must be accepted."""
    assert validate_case_id("CASE-001") == "CASE-001"
    assert validate_case_id("FIR_2026_99") == "FIR_2026_99"
    assert validate_case_id("a" * 64) == "a" * 64


def test_case_id_validation_path_traversal_and_invalid():
    """Path traversal and invalid characters must raise ValueError."""
    invalid_cases = [
        "../traversal",
        "..\\windows_traversal",
        "/absolute/path",
        "case/sub",
        "case with spaces",
        "case:colon",
        "case+plus",
        "",  # empty
        "a" * 65,  # too long
        "case.dot",
        "case@symbol",
    ]
    for case in invalid_cases:
        with pytest.raises(ValueError):
            validate_case_id(case)


def test_safe_filename():
    """Unsafe filesystem characters must be cleanly replaced."""
    assert safe_filename("DOC-123:p001+abc") == "DOC-123_p001_abc"
    assert safe_filename('bad<file>"name/test\\1|2?3*4') == "bad_file_name_test_1_2_3_4"


def test_deterministic_ids():
    """ID generation functions must be deterministic and stable."""
    doc_id = make_doc_id("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert doc_id == "DOC-e3b0c44298fc"

    assert make_unit_id_page(doc_id, 1) == "DOC-e3b0c44298fc:p001"
    assert make_unit_id_line(doc_id, 1, 5) == "DOC-e3b0c44298fc:p001:l005"
    assert make_unit_id_row(doc_id, 0, 10) == "DOC-e3b0c44298fc:s00:r000010"
    assert make_unit_id_text_line(doc_id, 15) == "DOC-e3b0c44298fc:l000015"
    assert make_unit_id_json(doc_id, "/parties/0/name") == "DOC-e3b0c44298fc:j:parties/0/name"

    m_id1 = make_mention_id(doc_id, "DOC-e3b0c44298fc:p001", "PERSON", "Ramesh", 0)
    m_id2 = make_mention_id(doc_id, "DOC-e3b0c44298fc:p001", "PERSON", "Ramesh", 0)
    assert m_id1 == m_id2
    assert m_id1.startswith("M-")
    assert len(m_id1) == 14  # 'M-' + 12 hex chars

    r_id = make_rel_id(doc_id, "DOC-e3b0c44298fc:p001", "USES_PHONE", m_id1, "M-other", 0)
    assert r_id.startswith("R-")
    assert len(r_id) == 14

    e_id = make_event_id(doc_id, "DOC-e3b0c44298fc:p001", "CALL", "Incoming call", 0)
    assert e_id.startswith("E-")
    assert len(e_id) == 14

    agg_id = make_aggregate_id("case-1", "CALLED", m_id1, "M-other")
    assert agg_id.startswith("AGG-")

    rev_id = make_review_id("case-1", "low_trust_identifier", m_id1, "review OCR phone")
    assert rev_id.startswith("REV-")

    rej_id = make_rejection_id("case-1", doc_id, "quote_not_found", "Quote absent")
    assert rej_id.startswith("REJ-")

    sug_id = make_suggestion_id("case-1", m_id1, "ENT-001")
    assert sug_id.startswith("SUG-")

    act_id = make_action_id()
    assert act_id.startswith("ACT-")

    run_id = make_run_id()
    assert run_id.startswith("RUN-")
    assert ":" not in run_id
    assert "+" not in run_id

    idemp_key = make_idempotency_key(
        "sha256hex", "0.1.0", "tesseract", "5.3", ["eng"], "mock", "none", "v1", "1.0.0", "1"
    )
    assert len(idemp_key) == 64


def test_model_schema_lint():
    """Hand-written provider schema must strictly pass provider schema lint rules."""
    errors = lint_provider_schema(MODEL_SCHEMA, max_depth=4)
    assert errors == [], f"Provider schema lint errors: {errors}"


def test_validate_model_output():
    """validate_model_output must accept valid outputs and reject schema violations."""
    valid_payload = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "suspect",
                "unit_id": "DOC-1:p001",
                "quote": "Suspect Vikram Singh was seen",
                "attributes": [
                    {
                        "name": "age",
                        "value_text": "34",
                        "quote": "aged about 34 years",
                    }
                ],
            }
        ],
        "relationships": [
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh uses mobile",
            }
        ],
        "events": [
            {
                "type": "CALL",
                "description": "Phone call made",
                "time_text": "2026-10-12 14:00",
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p001",
                "quote": "Call placed at 14:00",
            }
        ],
        "notes": ["Note regarding suspect identity"],
    }
    validated = validate_model_output(valid_payload)
    assert validated["mentions"][0]["local_id"] == "m1"

    # Reject unknown extra fields (extra=forbid)
    invalid_extra = dict(valid_payload)
    invalid_extra["mentions"] = [dict(valid_payload["mentions"][0], unexpected_field="bad")]
    with pytest.raises(ValueError):
        validate_model_output(invalid_extra)

    # Reject invalid enum
    invalid_enum = dict(valid_payload)
    invalid_enum["mentions"] = [dict(valid_payload["mentions"][0], type="UNKNOWN_TYPE")]
    with pytest.raises(ValueError):
        validate_model_output(invalid_enum)


def test_record_models_roundtrip_and_extra_forbid():
    """Every record model must roundtrip JSON and reject unknown fields (extra='forbid')."""
    source = SourceRef(
        doc_id="DOC-123456789012",
        file_name="fir_sample.pdf",
        file_sha256="1234567890123456789012345678901234567890123456789012345678901234",
        unit_id="DOC-123456789012:p001",
        unit_kind=UnitKind.PAGE,
        page=1,
        text_origin=Origin.PDF_TEXT,
        quote="Accused Vikram Singh",
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )

    ocr = OcrInfo(
        level=OcrLevel.WORD,
        min=85.0,
        mean=94.2,
        engine="tesseract",
        langs=["eng", "hin"],
    )

    mention = Mention(
        mention_id="M-123456789012",
        case_id="case-101",
        doc_id="DOC-123456789012",
        type=EntityType.PERSON,
        surface_text="विक्रम सिंह / Vikram Singh",
        normalized_value="VIKRAM SINGH",
        normalization_status=NormalizationStatus.OK,
        checks=[ValidationCheck(name="name_format", passed=True)],
        stated_role=StatedRole.ACCUSED,
        attributes=[
            MentionAttribute(name=AttrName.AGE, value_text="35", source=source),
            MentionAttribute(name=AttrName.FATHER_NAME, value_text="राम सिंह", source=source),
        ],
        origin=Origin.PDF_TEXT,
        ocr=ocr,
        identifier_trust=IdentifierTrust.STRONG,
        review_flags=[ReviewKind.ROLE_INFERRED],
        source=source,
    )

    # Assert UTF-8 roundtrip with Indic script
    mention_json = mention.model_dump_json()
    mention_reloaded = Mention.model_validate_json(mention_json)
    assert mention_reloaded == mention
    assert "विक्रम सिंह" in mention_reloaded.surface_text

    rel = Relationship(
        rel_id="R-123456789012",
        case_id="case-101",
        type=RelType.USES_PHONE,
        subject_mention_id="M-123456789012",
        object_mention_id="M-987654321098",
        assertion=Assertion.STATED,
        origin=Origin.PDF_TEXT,
        source=source,
    )
    rel_json = rel.model_dump_json()
    assert Relationship.model_validate_json(rel_json) == rel

    event = Event(
        event_id="E-123456789012",
        case_id="case-101",
        type=EventType.INCIDENT,
        description="Theft reported at Connaught Place",
        time=EventTime(
            original_text="12/10/2026 14:30 IST",
            normalized_iso="2026-10-12T14:30:00+05:30",
            timezone="Asia/Kolkata",
            ambiguity=TimeAmbiguity.NONE,
        ),
        participants=[EventParticipant(mention_id="M-123456789012", role="accused")],
        amount=EventAmount(value_text="₹50,000", decimal=50000.0, currency="INR"),
        origin=Origin.PDF_TEXT,
        source=source,
    )
    assert Event.model_validate_json(event.model_dump_json()) == event

    agg = Aggregate(
        aggregate_id="AGG-1234567890",
        case_id="case-101",
        type=RelType.CALLED,
        subject_mention_id="M-123456789012",
        object_mention_id="M-987654321098",
        count=15,
        total_duration_s=1240.0,
        sample_sources=[source],
    )
    assert Aggregate.model_validate_json(agg.model_dump_json()) == agg

    rev = ReviewItem(
        review_id="REV-1234567890",
        case_id="case-101",
        kind=ReviewKind.LOW_TRUST_IDENTIFIER,
        target_ids=["M-123456789012"],
        detail="OCR confidence low for phone number",
        status=ReviewItemStatus.OPEN,
    )
    assert ReviewItem.model_validate_json(rev.model_dump_json()) == rev

    rej = Rejection(
        rejection_id="REJ-1234567890",
        case_id="case-101",
        doc_id="DOC-123456789012",
        kind=RejectionKind.QUOTE_NOT_FOUND,
        reason="Model quote did not match text layer",
        model_item_excerpt="Sample excerpt",
    )
    assert Rejection.model_validate_json(rej.model_dump_json()) == rej

    doc_rec = DocumentRecord(
        doc_id="DOC-123456789012",
        file_name="fir_sample.pdf",
        file_sha256="1234567890123456789012345678901234567890123456789012345678901234",
        size_bytes=10240,
        detected_type="pdf",
        status=DocumentStatus.PROCESSED,
        pages=[PageInfo(page=1, method=PageMethod.PDF_TEXT, chars=1200)],
        sheets=[SheetInfo(name="Sheet1", state=SheetState.VISIBLE, rows=100)],
    )
    assert DocumentRecord.model_validate_json(doc_rec.model_dump_json()) == doc_rec

    run_meta = RunMeta(
        run_id="RUN-20261013T120000Z-a1b2c3",
        started_at="2026-10-13T12:00:00Z",
        pipeline_version="0.1.0",
        prompt_version="extract-v1",
        provider="mock",
        model="mock-v1",
        ocr_engine="tesseract",
        ocr_version="5.3",
        normalization_version="1",
        resolver_version="1",
        idempotency_key="a" * 64,
    )
    assert RunMeta.model_validate_json(run_meta.model_dump_json()) == run_meta

    case_result = CaseResult(
        case_id="case-101",
        run=run_meta,
        state=JobState.COMPLETED,
        documents=[doc_rec],
        mentions=[mention],
        relationships=[rel],
        events=[event],
        aggregates=[agg],
        review_items=[rev],
        rejections=[rej],
    )
    assert CaseResult.model_validate_json(case_result.model_dump_json()) == case_result

    suggestion = ResolutionSuggestion(
        suggestion_id="SUG-1234567890",
        case_id="case-101",
        mention_id="M-123456789012",
        candidate_entity_id="ENT-555",
        status=SuggestionStatus.CANDIDATE,
        heuristic_rank=0.88,
        signals=[
            Signal(
                kind="exact_identifier",
                polarity=SignalPolarity.SUPPORTS,
                detail="Matching verified phone number",
                sources=[source],
            )
        ],
        explanation="Matched via strong identifier link",
    )
    assert ResolutionSuggestion.model_validate_json(suggestion.model_dump_json()) == suggestion

    action = ReviewAction(
        action_id="ACT-123456789012",
        type=ReviewActionType.APPROVE_MATCH,
        actor="inspector_sharma",
        at="2026-10-13T12:05:00Z",
        reason="Verified phone and name correlation",
        target_ids=["SUG-1234567890"],
        payload={"approved": True},
        prev_hash="0" * 64,
        entry_hash="1" * 64,
    )
    assert ReviewAction.model_validate_json(action.model_dump_json()) == action

    # Test extra='forbid' on models
    with pytest.raises(ValidationError):
        Mention.model_validate(dict(mention.model_dump(), unexpected_extra_field="fail"))
    with pytest.raises(ValidationError):
        SourceRef.model_validate(dict(source.model_dump(), unexpected_extra_field="fail"))
    with pytest.raises(ValidationError):
        CaseResult.model_validate(dict(case_result.model_dump(), unexpected_extra_field="fail"))


def test_path_traversal_blocked_in_pydantic_case_id():
    """Any Pydantic model with case_id must reject directory traversal at initialization."""
    with pytest.raises(ValidationError):
        CaseResult(
            case_id="../traversal_case",
            run=RunMeta(
                run_id="RUN-20261013T120000Z-a1b2c3",
                started_at="2026-10-13T12:00:00Z",
                pipeline_version="0.1.0",
                prompt_version="extract-v1",
                provider="mock",
                model="mock-v1",
                ocr_engine="tesseract",
                ocr_version="5.3",
                normalization_version="1",
                resolver_version="1",
                idempotency_key="a" * 64,
            ),
            state=JobState.COMPLETED,
        )


def test_export_schemas(tmp_path: Path):
    """export_schemas must generate valid JSON schema files for all models."""
    exported = export_schemas(tmp_path)
    assert len(exported) >= 14
    for _name, schema_path in exported.items():
        assert schema_path.exists()
        with open(schema_path, encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
            assert "type" in data or "$defs" in data or "properties" in data
