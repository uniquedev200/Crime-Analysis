"""End-to-end tests for ATLAS Dev 3 HTML report generation.

All tests are marked @pytest.mark.gate4.
Tests:
- Valid facts rendering with document tabs, OCR badges, and audit log.
- Strict XSS escaping: quotes, notes, attributes containing script tags render inert.
- Mock provider honesty banner display when provider == 'mock'.
- Case isolation: foreign case data never leaks into the case report.
- UTF-8 file write and read back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.contracts.enums import (
    Assertion,
    AttrName,
    DocumentStatus,
    EntityType,
    EventType,
    IdentifierTrust,
    JobState,
    OcrLevel,
    Origin,
    QuoteStatus,
    RelType,
    ReviewActionType,
    ReviewItemStatus,
    ReviewKind,
    SignalPolarity,
    SuggestionStatus,
    UnitKind,
)
from atlas.contracts.records import (
    CaseResult,
    DocumentRecord,
    Event,
    EventParticipant,
    Mention,
    MentionAttribute,
    OcrInfo,
    Relationship,
    ResolutionSuggestion,
    ReviewAction,
    ReviewItem,
    RunMeta,
    Signal,
    SourceRef,
)
from atlas.output.report_html import generate_report_html, render_report_html, write_report_html


def _build_dummy_run_meta(provider: str = "mock") -> RunMeta:
    return RunMeta(
        run_id="RUN-20261016T120000Z-abcdef",
        started_at="2026-10-16T12:00:00Z",
        finished_at="2026-10-16T12:05:00Z",
        pipeline_version="3.3.0",
        schema_version="1.0.0",
        prompt_version="1.0.0",
        provider=provider,
        model="gpt-4o" if provider != "mock" else "mock-extraction-model",
        temperature=0.0,
        ocr_engine="tesseract",
        ocr_version="1.0.0",
        ocr_langs=["eng"],
        normalization_version="1.0.0",
        resolver_version="1.0.0",
        idempotency_key="0123456789abcdef" * 4,
    )


def _build_dummy_source_ref(
    doc_id: str = "DOC-A1",
    file_name: str = "FIR_A.pdf",
    quote: str = "Accused Vikram Singh alias Vicky S/o Harbans Singh",
    origin: Origin = Origin.OCR,
    bbox: list[float] | None = None,
) -> SourceRef:
    return SourceRef(
        doc_id=doc_id,
        file_name=file_name,
        file_sha256="a" * 64,
        unit_id=f"{doc_id}:p001",
        unit_kind=UnitKind.PAGE,
        text_origin=origin,
        quote=quote,
        quote_status=QuoteStatus.VERIFIED,
        page=1,
        bbox=bbox or [100.0, 50.0, 120.0, 200.0],
    )


@pytest.mark.gate4
def test_report_html_generation_valid_facts(tmp_path: Path) -> None:
    """Render report.html with valid facts, OCR info, suggestions, and audit trail."""
    case_id = "CASE-A-001"
    doc_id = "DOC-FIR-A"

    doc = DocumentRecord(
        doc_id=doc_id,
        file_name="FIR_A.pdf",
        file_sha256="1234567890abcdef" * 4,
        size_bytes=10240,
        detected_type="pdf",
        status=DocumentStatus.PROCESSED,
        case_id=case_id,
    )

    source = _build_dummy_source_ref(
        doc_id=doc_id,
        file_name="FIR_A.pdf",
        quote="Accused phone: +919876543210",
        origin=Origin.OCR,
        bbox=[120.0, 45.0, 140.0, 180.0],
    )

    ocr_info = OcrInfo(
        level=OcrLevel.WORD,
        mean=88.5,
        min=72.0,
        score_kind="engine_score_not_probability",
        engine="tesseract",
        langs=["eng"],
    )

    mention_phone = Mention(
        mention_id="M-PHONE-01",
        case_id=case_id,
        doc_id=doc_id,
        type=EntityType.PHONE,
        surface_text="+919876543210",
        normalized_value="+919876543210",
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        origin=Origin.OCR,
        ocr=ocr_info,
        review_flags=[ReviewKind.LOW_TRUST_IDENTIFIER],
        source=source,
    )

    mention_person = Mention(
        mention_id="M-PERSON-01",
        case_id=case_id,
        doc_id=doc_id,
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="Vikram Singh",
        origin=Origin.OCR,
        attributes=[
            MentionAttribute(name=AttrName.FATHER_NAME, value_text="Harbans Singh"),
            MentionAttribute(name=AttrName.AGE, value_text="32"),
        ],
        source=source,
    )

    rel = Relationship(
        rel_id="R-01",
        case_id=case_id,
        type=RelType.USES_PHONE,
        subject_mention_id="M-PERSON-01",
        object_mention_id="M-PHONE-01",
        assertion=Assertion.STATED,
        origin=Origin.OCR,
        source=source,
    )

    event = Event(
        event_id="E-01",
        case_id=case_id,
        type=EventType.INCIDENT,
        description="Theft reported at Connaught Place",
        participants=[EventParticipant(mention_id="M-PERSON-01", role="accused")],
        origin=Origin.OCR,
        source=source,
    )

    review_item = ReviewItem(
        review_id="REV-01",
        case_id=case_id,
        kind=ReviewKind.LOW_TRUST_IDENTIFIER,
        target_ids=["M-PHONE-01"],
        detail="OCR phone confidence below threshold, confirmation required",
        status=ReviewItemStatus.OPEN,
    )

    case_result = CaseResult(
        schema_version="1.0.0",
        case_id=case_id,
        run=_build_dummy_run_meta(provider="mock"),
        state=JobState.COMPLETED_WITH_WARNINGS,
        documents=[doc],
        mentions=[mention_person, mention_phone],
        relationships=[rel],
        events=[event],
        review_items=[review_item],
    )

    suggestion = ResolutionSuggestion(
        suggestion_id="SUG-01",
        case_id=case_id,
        mention_id="M-PERSON-01",
        candidate_entity_id="PERSON:CASE-B-002:vicky",
        candidate_case_id="CASE-B-002",
        status=SuggestionStatus.NEEDS_REVIEW,
        heuristic_rank=0.85,
        rank_note="heuristic ordering, not a probability",
        signals=[
            Signal(
                kind="shared_identifier",
                polarity=SignalPolarity.SUPPORTS,
                detail="Shared phone number +919876543210",
            )
        ],
        explanation="Candidate matches on shared phone number but names are dissimilar",
        requires_human_decision=True,
    )

    audit_entry = ReviewAction(
        action_id="ACT-01",
        type=ReviewActionType.CONFIRM_IDENTIFIER,
        actor="lead_investigator",
        at="2026-10-16T12:10:00Z",
        reason="Visual check of scanned FIR confirms phone digits +919876543210",
        target_ids=["M-PHONE-01"],
        case_id=case_id,
        prev_hash="0" * 64,
        entry_hash="a1b2c3d4e5f6" + "0" * 52,
    )

    raw_texts = {doc_id: "Police Report: FIR details. Accused phone: +919876543210 registered."}

    html_content = render_report_html(
        case_result=case_result,
        suggestions=[suggestion],
        audit_entries=[audit_entry],
        raw_texts=raw_texts,
    )

    # Core verifications
    assert case_id in html_content
    assert "RUN-20261016T120000Z-abcdef" in html_content
    assert "FIR_A.pdf" in html_content
    assert "+919876543210" in html_content
    assert "Vikram Singh" in html_content
    assert "Harbans Singh" in html_content
    assert "review_required" in html_content
    assert "BBox: [120.0, 45.0, 140.0, 180.0]" in html_content
    assert "heuristic ordering, not a probability" in html_content
    assert "PERSON:CASE-B-002:vicky" in html_content
    assert "ACT-01" in html_content
    assert "lead_investigator" in html_content
    assert '<mark class="quote-highlight">' in html_content


@pytest.mark.gate4
def test_report_html_xss_escaping() -> None:
    """XSS strings injected in quote, attributes, or notes render inert."""
    case_id = "CASE-XSS-001"
    xss_payload = "<script>alert('xss_attack')</script>"

    source = _build_dummy_source_ref(
        doc_id="DOC-XSS",
        file_name="xss_doc.txt",
        quote=xss_payload,
        origin=Origin.TEXT_FILE,
    )

    mention = Mention(
        mention_id="M-XSS",
        case_id=case_id,
        doc_id="DOC-XSS",
        type=EntityType.PERSON,
        surface_text=xss_payload,
        normalized_value=xss_payload,
        origin=Origin.TEXT_FILE,
        attributes=[
            MentionAttribute(
                name=AttrName.FATHER_NAME,
                value_text=xss_payload,
            )
        ],
        source=source,
    )

    review_item = ReviewItem(
        review_id="REV-XSS",
        case_id=case_id,
        kind=ReviewKind.LOW_TRUST_IDENTIFIER,
        detail=xss_payload,
        status=ReviewItemStatus.OPEN,
    )

    doc = DocumentRecord(
        doc_id="DOC-XSS",
        file_name="xss_doc.txt",
        file_sha256="b" * 64,
        size_bytes=512,
        detected_type="text",
        status=DocumentStatus.PROCESSED,
        case_id=case_id,
    )

    case_result = CaseResult(
        schema_version="1.0.0",
        case_id=case_id,
        run=_build_dummy_run_meta(provider="mock"),
        state=JobState.COMPLETED,
        documents=[doc],
        mentions=[mention],
        review_items=[review_item],
    )

    raw_texts = {"DOC-XSS": f"Raw document text containing {xss_payload} inside."}

    html_content = render_report_html(
        case_result=case_result,
        raw_texts=raw_texts,
    )

    # The string "<script>alert" must NEVER occur anywhere in raw unescaped form
    assert "<script>alert" not in html_content

    # The HTML-escaped equivalent must be present
    assert "&lt;script&gt;alert(&#39;xss_attack&#39;)&lt;/script&gt;" in html_content or (
        "&lt;script&gt;alert('xss_attack')&lt;/script&gt;" in html_content
    )


@pytest.mark.gate4
def test_report_html_mock_provider_honesty_banner() -> None:
    """Mock honesty banner displayed when provider == 'mock', omitted otherwise."""
    case_id = "CASE-MOCK-001"
    doc = DocumentRecord(
        doc_id="DOC-01",
        file_name="test.txt",
        file_sha256="c" * 64,
        size_bytes=100,
        detected_type="text",
        status=DocumentStatus.PROCESSED,
        case_id=case_id,
    )

    # 1. With provider='mock'
    result_mock = CaseResult(
        schema_version="1.0.0",
        case_id=case_id,
        run=_build_dummy_run_meta(provider="mock"),
        state=JobState.COMPLETED,
        documents=[doc],
    )
    html_mock = generate_report_html(result_mock)
    assert "SCRIPTED MOCK PROVIDER: not live extraction" in html_mock

    # 2. With provider='openai'
    result_live = CaseResult(
        schema_version="1.0.0",
        case_id=case_id,
        run=_build_dummy_run_meta(provider="openai"),
        state=JobState.COMPLETED,
        documents=[doc],
    )
    html_live = render_report_html(result_live)
    assert "SCRIPTED MOCK PROVIDER: not live extraction" not in html_live


@pytest.mark.gate4
def test_report_html_case_isolation() -> None:
    """Foreign case entities, mentions, and suggestions do not appear in the report."""
    case_id_a = "CASE-A-001"
    case_id_b = "CASE-B-002"

    doc_a = DocumentRecord(
        doc_id="DOC-A",
        file_name="case_a_doc.txt",
        file_sha256="d" * 64,
        size_bytes=200,
        detected_type="text",
        status=DocumentStatus.PROCESSED,
        case_id=case_id_a,
    )

    mention_a = Mention(
        mention_id="M-A-1",
        case_id=case_id_a,
        doc_id="DOC-A",
        type=EntityType.PERSON,
        surface_text="Authorized Entity Case A",
        origin=Origin.TEXT_FILE,
        source=_build_dummy_source_ref(doc_id="DOC-A", file_name="case_a_doc.txt", origin=Origin.TEXT_FILE),
    )

    # Maliciously included foreign mention
    mention_foreign = Mention(
        mention_id="M-B-FOREIGN",
        case_id=case_id_b,
        doc_id="DOC-B",
        type=EntityType.PERSON,
        surface_text="SECRET_FOREIGN_ENTITY_DATA",
        origin=Origin.TEXT_FILE,
        source=_build_dummy_source_ref(doc_id="DOC-B", file_name="case_b_doc.txt", origin=Origin.TEXT_FILE),
    )

    result_a = CaseResult(
        schema_version="1.0.0",
        case_id=case_id_a,
        run=_build_dummy_run_meta(provider="mock"),
        state=JobState.COMPLETED,
        documents=[doc_a],
        mentions=[mention_a, mention_foreign],
    )

    # Maliciously included foreign suggestion
    foreign_suggestion = ResolutionSuggestion(
        suggestion_id="SUG-FOREIGN",
        case_id=case_id_b,  # Belongs to Case B
        mention_id="M-B-FOREIGN",
        candidate_entity_id="FOREIGN-CANDIDATE",
        status=SuggestionStatus.CANDIDATE,
        explanation="Secret foreign investigation note",
        requires_human_decision=True,
    )

    # Maliciously included foreign audit entry
    foreign_audit = ReviewAction(
        action_id="ACT-FOREIGN",
        type=ReviewActionType.APPROVE_MATCH,
        actor="foreign_actor",
        at="2026-10-16T12:00:00Z",
        reason="Foreign review action",
        target_ids=["TARGET-B"],
        case_id=case_id_b,
        prev_hash="0" * 64,
        entry_hash="f" * 64,
    )

    html_a = render_report_html(
        case_result=result_a,
        suggestions=[foreign_suggestion],
        audit_entries=[foreign_audit],
    )

    assert "Authorized Entity Case A" in html_a
    assert "SECRET_FOREIGN_ENTITY_DATA" not in html_a
    assert "SUG-FOREIGN" not in html_a
    assert "Secret foreign investigation note" not in html_a
    assert "ACT-FOREIGN" not in html_a


@pytest.mark.gate4
def test_write_report_html_file(tmp_path: Path) -> None:
    """write_report_html writes UTF-8 HTML file to disk."""
    case_id = "CASE-WRITE-001"
    doc = DocumentRecord(
        doc_id="DOC-W",
        file_name="w.txt",
        file_sha256="e" * 64,
        size_bytes=100,
        detected_type="text",
        status=DocumentStatus.PROCESSED,
        case_id=case_id,
    )
    result = CaseResult(
        schema_version="1.0.0",
        case_id=case_id,
        run=_build_dummy_run_meta(provider="mock"),
        state=JobState.COMPLETED,
        documents=[doc],
    )

    target_file = tmp_path / "outputs" / case_id / "report.html"
    written_path = write_report_html(result, target_file)

    assert written_path == target_file
    assert target_file.is_file()
    content = target_file.read_text(encoding="utf-8")
    assert f"Case ID: {case_id}" in content
    assert "SCRIPTED MOCK PROVIDER: not live extraction" in content
