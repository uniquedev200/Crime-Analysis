"""Adversarial test suite: Malformed model output handling and schema enforcement.

Tests coverage:
1. Extra fields in mention, relationship, and event (rejected / schema violation).
2. Wrong enum value in role, entity type, relation type (Pydantic validation failure & verifier rejection).
3. Huge string in surface_text or quote (rejected or bounded).
4. Duplicate local_ids in a single response (handled safely without crash).
5. Quote from another case or another document (unit_not_in_chunk / quote_not_found).
6. Quote shortened to < 3 characters (rejected with quote_not_found).
7. Model attempting to "fix" OCR typo in its quote (rejected with quote_not_found).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlas.contracts.enums import EntityType, EventType, RejectionKind, RelType, StatedRole
from atlas.contracts.model_schema import (
    ModelEventOutput,
    ModelMentionOutput,
    ModelRelationshipOutput,
)
from atlas.extract.units import Unit
from atlas.provenance.verify import verify_model_output

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
def test_extra_fields_in_pydantic_models_raise_validation_error() -> None:
    """Extra fields in model outputs must be forbidden by Pydantic (extra='forbid')."""
    # 1. Mention with extra field
    with pytest.raises(ValidationError) as exc_info:
        ModelMentionOutput(
            local_id="m1",
            type=EntityType.PERSON,
            surface_text="Ramesh",
            role_stated=StatedRole.SUSPECT,
            unit_id="DOC-1:p001",
            quote="Ramesh was observed",
            attributes=[],
            untrusted_extra="payload",  # Forbidden extra field
        )
    assert "extra_forbidden" in str(exc_info.value)

    # 2. Relationship with extra field
    with pytest.raises(ValidationError) as exc_info:
        ModelRelationshipOutput(
            type=RelType.USES_PHONE,
            subject_local_id="m1",
            object_local_id="m2",
            unit_id="DOC-1:p001",
            quote="Ramesh used phone",
            sql_injection="DROP TABLE mentions;",  # Forbidden extra field
        )
    assert "extra_forbidden" in str(exc_info.value)

    # 3. Event with extra field
    with pytest.raises(ValidationError) as exc_info:
        ModelEventOutput(
            type=EventType.INCIDENT,
            description="Theft reported",
            time_text="2023-01-01",
            participant_local_ids=["m1"],
            location_local_id=None,
            unit_id="DOC-1:p001",
            quote="Theft reported on Jan 1",
            injected_flag=True,  # Forbidden extra field
        )
    assert "extra_forbidden" in str(exc_info.value)


@pytest.mark.gate5
def test_extra_fields_in_raw_dict_rejected_by_verify_model_output() -> None:
    """Extra fields in raw LLM output dict must be flagged as SCHEMA_VIOLATION by verifier."""
    doc_id = "DOC-testextra01"
    case_id = "CASE-EXTRA-001"
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text="Ramesh was observed using phone 9876543210 during the incident.",
        method="pdf_text",
    )

    malformed_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Ramesh",
                "role_stated": "suspect",
                "unit_id": f"{doc_id}:p001",
                "quote": "Ramesh was observed",
                "attributes": [],
                "exploit_field": "injected_value",  # Extra field
            }
        ],
        "relationships": [
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": f"{doc_id}:p001",
                "quote": "Ramesh was observed using phone",
                "malicious_extra": 123,  # Extra field
            }
        ],
        "events": [
            {
                "type": "INCIDENT",
                "description": "incident occurred",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": f"{doc_id}:p001",
                "quote": "during the incident.",
                "overflow_field": "abc",  # Extra field
            }
        ],
        "notes": [],
    }

    mentions, rels, events, _reviews, rejections = verify_model_output(
        model_output=malformed_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    # All items with extra fields are rejected
    assert len(mentions) == 0
    assert len(rels) == 0
    assert len(events) == 0
    assert len(rejections) >= 1
    rejection_reasons = [r.reason for r in rejections]
    assert any("Unexpected extra fields" in r for r in rejection_reasons)


@pytest.mark.gate5
def test_wrong_enum_values_in_pydantic_and_verifier() -> None:
    """Invalid enum values must fail Pydantic validation and verifier schema checks."""
    # 1. Pydantic validation rejects unknown enum strings
    with pytest.raises(ValidationError):
        ModelMentionOutput(
            local_id="m1",
            type="SUPERHERO",  # type: ignore[arg-type]
            surface_text="Batman",
            role_stated="vigilante",  # type: ignore[arg-type]
            unit_id="DOC-1:p001",
            quote="Batman appeared",
            attributes=[],
        )

    # 2. Verifier rejects invalid enum strings in raw dict
    doc_id = "DOC-enum01"
    case_id = "CASE-ENUM-01"
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text="Unknown entity detected at scene.",
        method="pdf_text",
    )

    invalid_enum_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "CYBER_BOT",  # Invalid EntityType
                "surface_text": "Unknown entity",
                "role_stated": "adversary",  # Invalid StatedRole
                "unit_id": f"{doc_id}:p001",
                "quote": "Unknown entity",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=invalid_enum_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.SCHEMA_VIOLATION
    assert "Unknown entity type" in rejections[0].reason


@pytest.mark.gate5
def test_huge_string_in_surface_text_or_quote_bounded() -> None:
    """Huge strings (e.g. 50,000 chars) are rejected safely with bounded rejection excerpts."""
    doc_id = "DOC-huge01"
    case_id = "CASE-HUGE-01"
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text="Normal brief unit text for evidence.",
        method="pdf_text",
    )

    huge_quote = "A" * 50000
    huge_surface = "B" * 50000

    huge_quote_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Normal",
                "role_stated": None,
                "unit_id": f"{doc_id}:p001",
                "quote": huge_quote,
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=huge_quote_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND
    # Rejection excerpt must be strictly bounded to prevent memory/log exhaustion
    if rejections[0].model_item_excerpt:
        assert len(rejections[0].model_item_excerpt) <= 200

    # Huge surface_text not in quote
    huge_surface_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": huge_surface,
                "role_stated": None,
                "unit_id": f"{doc_id}:p001",
                "quote": "Normal brief unit text",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions2, _rels2, _events2, _reviews2, rejections2 = verify_model_output(
        model_output=huge_surface_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    assert len(mentions2) == 0
    assert len(rejections2) == 1
    assert rejections2[0].kind == RejectionKind.VALUE_NOT_IN_QUOTE
    if rejections2[0].model_item_excerpt:
        assert len(rejections2[0].model_item_excerpt) <= 200


@pytest.mark.gate5
def test_duplicate_local_ids_handled_safely() -> None:
    """Duplicate local_ids in model response must be handled deterministically without crashing."""
    doc_id = "DOC-duplocal01"
    case_id = "CASE-DUP-01"
    unit_text = "Ramesh Kumar met Suresh Sharma at the railway station."
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text=unit_text,
        method="pdf_text",
    )

    # Both mentions use local_id "m1"
    duplicate_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Ramesh Kumar",
                "role_stated": None,
                "unit_id": f"{doc_id}:p001",
                "quote": "Ramesh Kumar met",
                "attributes": [],
            },
            {
                "local_id": "m1",  # Duplicate local_id
                "type": "PERSON",
                "surface_text": "Suresh Sharma",
                "role_stated": None,
                "unit_id": f"{doc_id}:p001",
                "quote": "Suresh Sharma at",
                "attributes": [],
            },
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, _rejections = verify_model_output(
        model_output=duplicate_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    # Execution completes cleanly; both mentions are preserved with distinct mention_ids
    assert len(mentions) == 2
    assert mentions[0].mention_id != mentions[1].mention_id
    assert {m.surface_text for m in mentions} == {"Ramesh Kumar", "Suresh Sharma"}


@pytest.mark.gate5
def test_quote_from_another_case_or_document_rejected() -> None:
    """Quote pointing to a foreign unit_id or foreign document is rejected."""
    doc_id = "DOC-primary001"
    case_id = "CASE-PRIMARY-01"
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text="Case evidence on primary document.",
        method="pdf_text",
    )

    # Mention references foreign doc_id in unit_id
    foreign_unit_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Foreign Person",
                "role_stated": None,
                "unit_id": "DOC-FOREIGN999:p001",
                "quote": "Foreign Person was seen",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=foreign_unit_output,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.UNIT_NOT_IN_CHUNK


@pytest.mark.gate5
def test_quote_shortened_below_three_characters_rejected() -> None:
    """Quotes shorter than 3 characters must be rejected immediately per Section 5.4."""
    doc_id = "DOC-short001"
    case_id = "CASE-SHORT-01"
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text="A B CD EF G",
        method="pdf_text",
    )

    for short_quote in ["", "A", "CD"]:
        output = {
            "mentions": [
                {
                    "local_id": "m1",
                    "type": "PERSON",
                    "surface_text": "A",
                    "role_stated": None,
                    "unit_id": f"{doc_id}:p001",
                    "quote": short_quote,
                    "attributes": [],
                }
            ],
            "relationships": [],
            "events": [],
            "notes": [],
        }

        mentions, _rels, _events, _reviews, rejections = verify_model_output(
            model_output=output,
            chunk_units=[unit],
            case_id=case_id,
            doc_id=doc_id,
        )

        assert len(mentions) == 0
        assert len(rejections) == 1
        assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND
        assert "< 3 characters" in rejections[0].reason


@pytest.mark.gate5
def test_model_attempting_to_fix_ocr_typo_rejected() -> None:
    """Model attempting to correct OCR typos in quote instead of verbatim copying is rejected."""
    doc_id = "DOC-ocrtypo01"
    case_id = "CASE-TYPO-01"
    # The actual OCR text contains misrecognized characters: 'Rarnesh Kwnar'
    unit_text = "Suspect name recorded as Rarnesh Kwnar during interrogation."
    unit = Unit(
        unit_id=f"{doc_id}:p001",
        doc_id=doc_id,
        page=1,
        text=unit_text,
        method="ocr",
    )

    # Model tries to be helpful by fixing the typo in the quote: 'Ramesh Kumar'
    model_output_fixing_typo = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Ramesh Kumar",
                "role_stated": "suspect",
                "unit_id": f"{doc_id}:p001",
                "quote": "Suspect name recorded as Ramesh Kumar",  # 'Ramesh Kumar' does not exist in unit text!
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=model_output_fixing_typo,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    # Verifier must reject: quote is not verbatim substring
    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND

    # However, if the model provides the EXACT verbatim OCR text in quote, it succeeds:
    model_output_verbatim = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Rarnesh Kwnar",
                "role_stated": "suspect",
                "unit_id": f"{doc_id}:p001",
                "quote": "Suspect name recorded as Rarnesh Kwnar",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions_ok, _rels_ok, _events_ok, _reviews_ok, rejections_ok = verify_model_output(
        model_output=model_output_verbatim,
        chunk_units=[unit],
        case_id=case_id,
        doc_id=doc_id,
    )

    assert len(mentions_ok) == 1
    assert mentions_ok[0].surface_text == "Rarnesh Kwnar"
    assert len(rejections_ok) == 0
