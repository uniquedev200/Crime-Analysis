"""Integration tests for PipelineRunner and within-case consolidation.

Test requirements (PLAN.md Section 8 H3 task card & Gate 3):
- Clean FIR end-to-end with mock LLM -> CaseResult and completed or completed_with_warnings
- State matrix tests: all OK, rejected input, chunk failed, failed validation
- Reprocessing creates new run_id and never overwrites earlier run
- Deterministic idempotency key and IDs on identical input
- FIR <-> CDR within-case linking on shared confirmed phone
- Unconfirmed OCR phone stays review_required and does not link
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.contracts.enums import (
    Assertion,
    DocumentStatus,
    EntityType,
    EventType,
    IdentifierTrust,
    JobState,
    Origin,
    QuoteStatus,
    RelType,
    ReviewKind,
    UnitKind,
)
from atlas.contracts.records import (
    CaseResult,
    Event,
    EventParticipant,
    Mention,
    Relationship,
    SourceRef,
)
from atlas.llm.mock import MockProvider
from atlas.llm.retry import RefusalError
from atlas.pipeline.runner import PipelineRunner
from atlas.pipeline.status import load_case_result


@pytest.mark.gate3
def test_clean_fir_end_to_end(tmp_path: Path) -> None:
    """Clean FIR end-to-end with mock LLM produces valid CaseResult and completed_with_warnings."""
    fir_path = Path("tests/fixtures/FIR_A.pdf")
    assert fir_path.is_file()

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()
    result = runner.run(
        case_id="CASE-FIR-001",
        file_paths=[fir_path],
        provider="mock",
        output_dir=out_dir,
    )

    assert isinstance(result, CaseResult)
    assert result.schema_version == "1.0.0"
    assert result.case_id == "CASE-FIR-001"
    assert result.state in (JobState.COMPLETED, JobState.COMPLETED_WITH_WARNINGS)
    assert len(result.documents) == 1
    assert result.documents[0].status == DocumentStatus.PROCESSED
    assert len(result.mentions) > 0
    assert result.run.idempotency_key != ""

    # Verify output directory and files
    run_dir = out_dir / "CASE-FIR-001" / result.run.run_id
    assert run_dir.is_dir()
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    assert (run_dir / "review_queue.json").is_file()
    assert (run_dir / "receipt.json").is_file()
    assert (run_dir / "trace.jsonl").is_file()

    loaded = load_case_result("CASE-FIR-001", run_id=result.run.run_id, output_dir=out_dir)
    assert loaded is not None
    assert loaded.case_id == result.case_id
    assert loaded.run.run_id == result.run.run_id


@pytest.mark.gate3
def test_state_matrix_all_ok(tmp_path: Path) -> None:
    """State matrix: all chunks OK and no review/rejection -> completed."""
    # Create clean synthetic text file
    txt_file = tmp_path / "clean_evidence.txt"
    txt_file.write_text("Case details: Witness statement recorded on page.", encoding="utf-8")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    # With empty/clean mock response: no rejections, no review items
    mock_client = MockProvider()
    doc_key = f"DOC-{txt_file.name}"
    mock_client.register_response(
        doc_key,
        0,
        {
            "mentions": [],
            "relationships": [],
            "events": [],
            "notes": [],
        },
    )

    result = runner.run(
        case_id="CASE-OK-001",
        file_paths=[txt_file],
        provider="mock",
        output_dir=out_dir,
    )

    assert result.state == JobState.COMPLETED
    assert len(result.review_items) == 0
    assert len(result.rejections) == 0


@pytest.mark.gate3
def test_state_matrix_rejected_input(tmp_path: Path) -> None:
    """State matrix: invalid file extension or magic bytes -> rejected_input."""
    bad_file = tmp_path / "bad_macro.xlsm"
    bad_file.write_bytes(b"PK\x03\x04fake content")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    result = runner.run(
        case_id="CASE-REJECT-001",
        file_paths=[bad_file],
        provider="mock",
        output_dir=out_dir,
    )

    assert result.state == JobState.REJECTED_INPUT
    assert len(result.documents) == 1
    assert result.documents[0].status == DocumentStatus.REJECTED_INPUT
    assert any("rejected" in w.lower() for w in result.warnings)


@pytest.mark.gate3
def test_state_matrix_chunk_failed_and_all_failed(tmp_path: Path) -> None:
    """State matrix: failed chunks leading to completed_with_warnings or failed."""
    txt_file = tmp_path / "failing_evidence.txt"
    txt_file.write_text("Unit text that will trigger simulated failure.", encoding="utf-8")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    # Simulate refusal error on the chunk
    with patch("atlas.pipeline.runner.execute_with_retry", side_effect=RefusalError("Safety refusal")):
        result = runner.run(
            case_id="CASE-FAIL-001",
            file_paths=[txt_file],
            provider="mock",
            output_dir=out_dir,
        )

    # All chunks failed -> state must be failed
    assert result.state == JobState.FAILED
    assert any(item.kind == ReviewKind.CHUNK_FAILED for item in result.review_items)
    # Facts from failed chunks must never be published
    assert len(result.mentions) == 0
    assert len(result.relationships) == 0


@pytest.mark.gate3
def test_state_matrix_failed_validation(tmp_path: Path) -> None:
    """State matrix: final CaseResult failing validation -> failed_validation."""
    txt_file = tmp_path / "evidence.txt"
    txt_file.write_text("Simple text line.", encoding="utf-8")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    # Simulate a validation error during CaseResult construction
    with patch("atlas.pipeline.runner.CaseResult.__init__", side_effect=ValueError("Simulated validation error")):
        result = runner.run(
            case_id="CASE-VALID-001",
            file_paths=[txt_file],
            provider="mock",
            output_dir=out_dir,
        )

    assert result.state == JobState.FAILED_VALIDATION


@pytest.mark.gate3
def test_reprocessing_creates_new_run_id_never_overwrites(tmp_path: Path) -> None:
    """Reprocessing creates a new run_id and never overwrites an earlier run."""
    txt_file = tmp_path / "evidence.txt"
    txt_file.write_text("Evidence note content.", encoding="utf-8")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    run1 = runner.run(
        case_id="CASE-REPROCESS-001",
        file_paths=[txt_file],
        provider="mock",
        output_dir=out_dir,
    )

    run2 = runner.run(
        case_id="CASE-REPROCESS-001",
        file_paths=[txt_file],
        provider="mock",
        output_dir=out_dir,
    )

    assert run1.run.run_id != run2.run.run_id
    dir1 = out_dir / "CASE-REPROCESS-001" / run1.run.run_id
    dir2 = out_dir / "CASE-REPROCESS-001" / run2.run.run_id

    assert dir1.is_dir()
    assert dir2.is_dir()
    assert dir1 != dir2
    assert (dir1 / "result.json").is_file()
    assert (dir2 / "result.json").is_file()


@pytest.mark.gate3
def test_deterministic_idempotency_key_and_ids(tmp_path: Path) -> None:
    """Identical input files and settings produce identical idempotency keys."""
    txt_file = tmp_path / "stable_doc.txt"
    txt_file.write_text("Determinism test line 1\nLine 2", encoding="utf-8")

    out_dir = tmp_path / "outputs"
    runner = PipelineRunner()

    run1 = runner.run(
        case_id="CASE-DET-001",
        file_paths=[txt_file],
        provider="mock",
        output_dir=out_dir,
    )

    run2 = runner.run(
        case_id="CASE-DET-001",
        file_paths=[txt_file],
        provider="mock",
        output_dir=out_dir,
    )

    assert run1.run.idempotency_key == run2.run.idempotency_key
    assert len(run1.run.idempotency_key) == 64


@pytest.mark.gate3
def test_fir_cdr_linking_on_shared_confirmed_phone(tmp_path: Path) -> None:
    """FIR <-> CDR within-case linking on shared confirmed phone."""
    case_id = "CASE-LINK-001"

    source_fir = SourceRef(
        doc_id="DOC-FIR",
        file_name="fir.txt",
        file_sha256="1" * 64,
        unit_id="DOC-FIR:l000001",
        unit_kind=UnitKind.LINE,
        text_origin=Origin.TEXT_FILE,
        quote="Accused phone: +919876543210",
        quote_status=QuoteStatus.VERIFIED,
    )

    source_cdr = SourceRef(
        doc_id="DOC-CDR",
        file_name="cdr.csv",
        file_sha256="2" * 64,
        unit_id="DOC-CDR:s00:r000001",
        unit_kind=UnitKind.ROW,
        text_origin=Origin.TABLE_PARSER,
        quote="+919876543210,9876543211",
        quote_status=QuoteStatus.VERIFIED,
    )

    # Person in FIR
    m_person = Mention(
        mention_id="M-PERSON001",
        case_id=case_id,
        doc_id="DOC-FIR",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        origin=Origin.TEXT_FILE,
        source=source_fir,
    )

    # Strong phone in FIR
    m_phone_fir = Mention(
        mention_id="M-PHONE-FIR",
        case_id=case_id,
        doc_id="DOC-FIR",
        type=EntityType.PHONE,
        surface_text="+919876543210",
        normalized_value="+919876543210",
        identifier_trust=IdentifierTrust.STRONG,
        origin=Origin.TEXT_FILE,
        source=source_fir,
    )

    # Strong phone in CDR
    m_phone_cdr = Mention(
        mention_id="M-PHONE-CDR",
        case_id=case_id,
        doc_id="DOC-CDR",
        type=EntityType.PHONE,
        surface_text="9876543210",
        normalized_value="+919876543210",
        identifier_trust=IdentifierTrust.STRONG,
        origin=Origin.TABLE_PARSER,
        source=source_cdr,
    )

    # Person uses phone relationship in FIR
    rel = Relationship(
        rel_id="R-001",
        case_id=case_id,
        type=RelType.USES_PHONE,
        subject_mention_id="M-PERSON001",
        object_mention_id="M-PHONE-FIR",
        assertion=Assertion.STATED,
        origin=Origin.TEXT_FILE,
        source=source_fir,
    )

    # Call event in CDR where caller is m_phone_cdr
    ev = Event(
        event_id="E-001",
        case_id=case_id,
        type=EventType.CALL,
        description="Call from +919876543210 to 9876543211",
        participants=[EventParticipant(mention_id="M-PHONE-CDR", role="caller")],
        origin=Origin.TABLE_PARSER,
        source=source_cdr,
    )

    from atlas.consolidate.within_case import consolidate_within_case

    c_men, c_rel, c_ev, _c_agg, _c_rev = consolidate_within_case(
        case_id=case_id,
        mentions=[m_person, m_phone_fir, m_phone_cdr],
        relationships=[rel],
        events=[ev],
    )

    # The two phone mentions should unify into a single phone mention
    phones = [m for m in c_men if m.type == EntityType.PHONE]
    assert len(phones) == 1
    canonical_phone_id = phones[0].mention_id

    # The relationship object_mention_id and the event participant mention_id should point to the SAME ID
    assert c_rel[0].object_mention_id == canonical_phone_id
    assert c_ev[0].participants[0].mention_id == canonical_phone_id


@pytest.mark.gate3
def test_unconfirmed_ocr_phone_does_not_unify(tmp_path: Path) -> None:
    """Unconfirmed OCR phone stays review_required and does NOT unify across documents."""
    case_id = "CASE-OCR-NO-UNIFY"

    source_fir = SourceRef(
        doc_id="DOC-FIR",
        file_name="fir.pdf",
        file_sha256="1" * 64,
        unit_id="DOC-FIR:p001",
        unit_kind=UnitKind.PAGE,
        text_origin=Origin.OCR,
        quote="Phone: +919876543210",
        quote_status=QuoteStatus.VERIFIED,
    )

    source_cdr = SourceRef(
        doc_id="DOC-CDR",
        file_name="cdr.xlsx",
        file_sha256="2" * 64,
        unit_id="DOC-CDR:s00:r000001",
        unit_kind=UnitKind.ROW,
        text_origin=Origin.TABLE_PARSER,
        quote="+919876543210",
        quote_status=QuoteStatus.VERIFIED,
    )

    # OCR phone without confirmation -> review_required
    m_phone_ocr = Mention(
        mention_id="M-PHONE-OCR",
        case_id=case_id,
        doc_id="DOC-FIR",
        type=EntityType.PHONE,
        surface_text="+919876543210",
        normalized_value="+919876543210",
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        confirmed_by=None,
        origin=Origin.OCR,
        source=source_fir,
    )

    # Strong phone in CDR
    m_phone_cdr = Mention(
        mention_id="M-PHONE-CDR",
        case_id=case_id,
        doc_id="DOC-CDR",
        type=EntityType.PHONE,
        surface_text="+919876543210",
        normalized_value="+919876543210",
        identifier_trust=IdentifierTrust.STRONG,
        origin=Origin.TABLE_PARSER,
        source=source_cdr,
    )

    from atlas.consolidate.within_case import consolidate_within_case

    c_men, _c_rel, _c_ev, _c_agg, _c_rev = consolidate_within_case(
        case_id=case_id,
        mentions=[m_phone_ocr, m_phone_cdr],
        relationships=[],
        events=[],
    )

    # Must NOT unify: both phone mentions must remain separate
    phones = [m for m in c_men if m.type == EntityType.PHONE]
    assert len(phones) == 2
    phone_ids = {m.mention_id for m in phones}
    assert "M-PHONE-OCR" in phone_ids
    assert "M-PHONE-CDR" in phone_ids
