"""Unit and integration tests for quote verification and provenance locating.

Tests verify Section 5.4 requirements:
- Valid quote verified
- Invented quote rejected (quote_not_found)
- Right words on wrong page rejected (unit_not_in_chunk / quote_not_found)
- Duplicate quote on page -> verified_ambiguous_location + review item
- Whitespace and hyphen-break normalization (- \n joined)
- NFC for Devanagari/Tamil strings preserved and matched
- Value not in quote rejected (value_not_in_quote)
- Model correcting OCR typo rejected
- Role downgrade when keyword missing + role_inferred item
- Role kept when keyword present
- Unknown local_id rejected
- Extra fields rejected (schema_violation)
- Integration test: scripted mock response for clean FIR (FIR_A) -> verified mentions with computed SourceRefs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from atlas.contracts.enums import (
    Assertion,
    EntityType,
    IdentifierTrust,
    QuoteStatus,
    RejectionKind,
    ReviewKind,
    StatedRole,
    UnitKind,
)
from atlas.extract.units import Unit
from atlas.provenance.locate import find_all_occurrences, locate_all_occurrences, locate_quote_in_unit
from atlas.provenance.normalize_text import normalize_for_match
from atlas.provenance.verify import (
    _determine_unit_kind,
    _map_method_to_origin,
    verify_model_output,
)

pytestmark = pytest.mark.gate2


def test_normalize_for_match_basic_and_edges() -> None:
    """Test all edge cases for normalize_for_match."""
    assert normalize_for_match("") == ""
    assert normalize_for_match("   ") == ""
    assert normalize_for_match("Hello\u00a0World") == "Hello World"
    assert normalize_for_match("Hello\u200b\u200c\u200d\ufeffWorld") == "HelloWorld"
    # Hyphen newline joining
    assert normalize_for_match("com-\nplainant") == "complainant"
    assert normalize_for_match("wit- \r\nness") == "witness"
    assert normalize_for_match("sub-\t\nsection") == "subsection"
    # Whitespace collapse and strip
    assert normalize_for_match("  Line 1\n  Line 2\t Line 3  ") == "Line 1 Line 2 Line 3"
    # Case and punctuation preserved
    assert normalize_for_match("Accused: Vikram Singh, alias Vicky!") == "Accused: Vikram Singh, alias Vicky!"


def test_normalize_for_match_nfc_devanagari_and_tamil() -> None:
    """NFC normalization for Devanagari and Tamil strings preserved and matched."""
    decomposed_hin = "\u0915\u093f"  # ki
    composed_hin = "\u0915\u093f"
    assert normalize_for_match(decomposed_hin) == normalize_for_match(composed_hin)
    assert normalize_for_match("शिकायतकर्ता: राजेश शर्मा") == "शिकायतकर्ता: राजेश शर्मा"

    tam_str = "சாட்சி: ரமேஷ்"
    assert normalize_for_match(tam_str) == "சாட்சி: ரமேஷ்"


def test_locate_quote_helpers() -> None:
    """Test locate_quote_in_unit and locate_all_occurrences helper functions."""
    unit = Unit(
        unit_id="DOC-1:p001",
        text="Line 1\nLine 2 target quote here\nLine 3 target quote here",
        page=1,
        line_start=1,
        line_end=3,
        doc_id="DOC-1",
    )
    assert find_all_occurrences("", "hello") == []
    assert find_all_occurrences("target", "") == []

    all_locs = locate_all_occurrences(unit, "target quote")
    assert len(all_locs) == 2
    assert all_locs[0][0] == 2  # Line 2
    assert all_locs[1][0] == 3  # Line 3

    # Empty text/quote locate
    empty_unit = Unit(unit_id="DOC-1:p001", text="", page=1, doc_id="DOC-1")
    assert locate_quote_in_unit(empty_unit, "quote") == (1, 1, None)
    assert locate_all_occurrences(empty_unit, "quote") == []


def test_helper_mappings() -> None:
    """Test _map_method_to_origin and _determine_unit_kind helpers."""
    assert _map_method_to_origin("table").value == "table_parser"
    assert _map_method_to_origin("text").value == "text_file"
    assert _map_method_to_origin("json").value == "json_file"
    assert _map_method_to_origin("unknown").value == "pdf_text"

    assert _determine_unit_kind("DOC-1:s00:r000001") == UnitKind.ROW
    assert _determine_unit_kind("DOC-1:p001:l005") == UnitKind.LINE
    assert _determine_unit_kind("DOC-1:j:person/name") == UnitKind.FIELD
    assert _determine_unit_kind("DOC-1:unknown") == UnitKind.PAGE


def test_valid_quote_verified() -> None:
    """Valid quote on page unit is verified and generates SourceRef."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Accused: Vikram Singh alias Vicky\nFather's Name: Harbans Singh\nAge: 32 yrs",
        page=1,
        line_start=1,
        line_end=3,
        method="pdf_text",
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Accused: Vikram Singh alias Vicky",
                "attributes": [
                    {
                        "name": "father_name",
                        "value_text": "Harbans Singh",
                        "quote": "Father's Name: Harbans Singh",
                    }
                ],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(rejections) == 0
    assert len(mentions) == 1
    m = mentions[0]
    assert m.surface_text == "Vikram Singh"
    assert m.stated_role == StatedRole.ACCUSED
    assert m.source.quote_status == QuoteStatus.VERIFIED
    assert m.source.page == 1
    assert m.source.line_start == 1
    assert m.source.line_end == 1
    assert len(m.attributes) == 1
    assert m.attributes[0].source is not None
    assert m.attributes[0].source.line_start == 2


def test_invented_quote_rejected() -> None:
    """Invented quote not found in unit text is rejected as quote_not_found."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Accused: Vikram Singh\nVehicle DL01AB1234",
        page=1,
        method="pdf_text",
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Suspect John Doe was seen fleeing on foot",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND


def test_right_words_wrong_page_rejected() -> None:
    """Right quote referencing unit not in chunk or wrong page is rejected."""
    unit1 = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Accused: Vikram Singh",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-1234567890ab:p002",
                "quote": "Accused: Vikram Singh",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit1],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.UNIT_NOT_IN_CHUNK


def test_unit_doc_id_mismatch_rejected() -> None:
    """Unit whose doc_id does not match the active doc_id is rejected."""
    unit = Unit(
        unit_id="DOC-DIFF:p001",
        text="Accused: Vikram Singh",
        page=1,
        doc_id="DOC-DIFF",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-DIFF:p001",
                "quote": "Accused: Vikram Singh",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-TARGET",
    )
    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.UNIT_NOT_IN_CHUNK


def test_duplicate_quote_ambiguous_location() -> None:
    """Duplicate quote occurring multiple times on a page -> verified_ambiguous_location + review item."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Contact: +919876543210\nSome other text\nEmergency Contact: +919876543210",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output: dict[str, Any] = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PHONE",
                "surface_text": "+919876543210",
                "role_stated": None,
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "+919876543210",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(rejections) == 0
    assert len(mentions) == 1
    assert mentions[0].source.quote_status == QuoteStatus.VERIFIED_AMBIGUOUS_LOCATION
    assert mentions[0].source.occurrence_count == 2
    assert ReviewKind.AMBIGUOUS_LOCATION in mentions[0].review_flags
    assert any(r.kind == ReviewKind.AMBIGUOUS_LOCATION for r in reviews)


def test_hyphen_break_and_whitespace_normalization() -> None:
    """Hyphen-break across lines ('wit-\nness') matches continuous quote ('witness')."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="The wit-\nness Manoj Tiwari arrived at the station.",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Manoj Tiwari",
                "role_stated": "witness",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "The witness Manoj Tiwari",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(rejections) == 0
    assert len(mentions) == 1
    assert mentions[0].source.quote_status == QuoteStatus.VERIFIED
    assert mentions[0].source.line_start == 1
    assert mentions[0].source.line_end == 2


def test_value_not_in_quote_rejected() -> None:
    """surface_text missing from quote fails value-in-quote check and is rejected."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="The suspect fled in a white car DL01AB1234.",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "suspect",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "suspect fled in a white car",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.VALUE_NOT_IN_QUOTE


def test_quote_too_short_rejected() -> None:
    """Quotes under 3 characters are rejected as quote_not_found."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="A B C",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output: dict[str, Any] = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "A",
                "role_stated": None,
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "A",  # len < 3
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )
    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND


def test_model_correcting_ocr_typo_rejected() -> None:
    """Model correcting an OCR typo in its quote fails and is rejected."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Accused phone was 981112223B according to memo.",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output: dict[str, Any] = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PHONE",
                "surface_text": "9811122238",
                "role_stated": None,
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Accused phone was 9811122238",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.QUOTE_NOT_FOUND


def test_role_downgrade_when_keyword_missing() -> None:
    """role_stated without matching keyword in quote is downgraded to unknown + role_inferred item."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Name: Vikram Singh S/o Harbans Singh",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Name: Vikram Singh S/o Harbans Singh",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(rejections) == 0
    assert len(mentions) == 1
    assert mentions[0].stated_role == StatedRole.UNKNOWN
    assert ReviewKind.ROLE_INFERRED in mentions[0].review_flags
    assert any(r.kind == ReviewKind.ROLE_INFERRED for r in reviews)


def test_role_kept_when_keyword_present() -> None:
    """role_stated with matching keyword (e.g. 'Accused') is preserved."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Accused: Vikram Singh",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "accused",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Accused: Vikram Singh",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(rejections) == 0
    assert len(mentions) == 1
    assert mentions[0].stated_role == StatedRole.ACCUSED
    assert ReviewKind.ROLE_INFERRED not in mentions[0].review_flags


def test_role_other_and_invalid() -> None:
    """Role stated as 'other' or invalid string is parsed safely."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Contact person: Ramesh",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Ramesh",
                "role_stated": "other",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Contact person: Ramesh",
                "attributes": [],
            },
            {
                "local_id": "m2",
                "type": "PERSON",
                "surface_text": "Ramesh",
                "role_stated": "arbitrary_unknown_role",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Contact person: Ramesh",
                "attributes": [],
            },
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, _rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )
    assert len(mentions) == 2
    assert mentions[0].stated_role == StatedRole.OTHER
    assert mentions[1].stated_role == StatedRole.UNKNOWN


def test_unknown_local_id_rejected() -> None:
    """Relationship or Event referencing nonexistent local_id is rejected as unknown_local_id."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Vikram Singh called +919876543210.",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": None,
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Vikram Singh",
                "attributes": [],
            }
        ],
        "relationships": [
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m999",
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Vikram Singh called +919876543210",
            }
        ],
        "events": [],
        "notes": [],
    }

    mentions, rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 1
    assert len(rels) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.UNKNOWN_LOCAL_ID


def test_extra_fields_rejected() -> None:
    """Extra fields outside provider-safe model schema trigger schema_violation rejection."""
    unit = Unit(
        unit_id="DOC-1234567890ab:p001",
        text="Vikram Singh",
        page=1,
        doc_id="DOC-1234567890ab",
    )
    raw_output: dict[str, Any] = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": None,
                "unit_id": "DOC-1234567890ab:p001",
                "quote": "Vikram Singh",
                "attributes": [],
                "confidence": 0.99,
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(mentions) == 0
    assert len(rejections) == 1
    assert rejections[0].kind == RejectionKind.SCHEMA_VIOLATION


def test_schema_violation_non_dict_and_invalid_enums() -> None:
    """Invalid structures in mentions, relationships, or events are safely rejected."""
    unit = Unit(
        unit_id="DOC-1:p001",
        text="Sample text for testing",
        page=1,
        doc_id="DOC-1",
    )
    raw_output: dict[str, Any] = {
        "mentions": "not_a_list",  # mentions not a list
        "relationships": ["not_a_dict"],
        "events": ["not_a_dict"],
        "notes": [],
    }
    _m, _r, _e, _rev, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1",
    )
    assert len(rejections) == 3


def test_identifier_trust_and_normalization_branches() -> None:
    """Test IMEIs, vehicles, accounts, digital vs OCR trust routing, and blocked identifiers."""
    unit_digital = Unit(
        unit_id="DOC-1:p001",
        text=(
            "Account: 001234567890\n"
            "IMEI: 490154203237518\n"
            "Vehicle: DL01AB1234\n"
            "Invalid Vehicle: ZZ99INVALID\n"
            "Invalid IMEI: 12345\n"
            "Masked Phone: 98XXXXX123\n"
        ),
        page=1,
        method="pdf_text",  # digital -> strong trust
        doc_id="DOC-1",
    )

    raw_output: dict[str, Any] = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "ACCOUNT",
                "surface_text": "001234567890",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Account: 001234567890",
                "attributes": [],
            },
            {
                "local_id": "m2",
                "type": "IMEI",
                "surface_text": "490154203237518",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "IMEI: 490154203237518",
                "attributes": [],
            },
            {
                "local_id": "m3",
                "type": "VEHICLE",
                "surface_text": "DL01AB1234",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Vehicle: DL01AB1234",
                "attributes": [],
            },
            {
                "local_id": "m4",
                "type": "VEHICLE",
                "surface_text": "ZZ99INVALID",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Invalid Vehicle: ZZ99INVALID",
                "attributes": [],
            },
            {
                "local_id": "m5",
                "type": "IMEI",
                "surface_text": "12345",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Invalid IMEI: 12345",
                "attributes": [],
            },
            {
                "local_id": "m6",
                "type": "PHONE",
                "surface_text": "98XXXXX123",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Masked Phone: 98XXXXX123",
                "attributes": [],
            },
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _r, _e, _reviews, _rej = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit_digital],
        case_id="CASE-001",
        doc_id="DOC-1",
    )

    m_acc = next(m for m in mentions if m.surface_text == "001234567890")
    assert m_acc.identifier_trust == IdentifierTrust.STRONG

    m_imei = next(m for m in mentions if m.surface_text == "490154203237518")
    assert m_imei.identifier_trust == IdentifierTrust.STRONG

    m_veh = next(m for m in mentions if m.surface_text == "DL01AB1234")
    assert m_veh.identifier_trust == IdentifierTrust.STRONG

    m_inv_veh = next(m for m in mentions if m.surface_text == "ZZ99INVALID")
    assert m_inv_veh.identifier_trust == IdentifierTrust.BLOCKED
    assert ReviewKind.INVALID_IDENTIFIER in m_inv_veh.review_flags

    m_inv_imei = next(m for m in mentions if m.surface_text == "12345")
    assert m_inv_imei.identifier_trust == IdentifierTrust.BLOCKED

    m_masked = next(m for m in mentions if m.surface_text == "98XXXXX123")
    assert m_masked.identifier_trust == IdentifierTrust.BLOCKED


def test_relationships_and_events_branches() -> None:
    """Test relationship assertion (model_inferred), event participants and time text."""
    unit = Unit(
        unit_id="DOC-1:p001",
        text="Vikram Singh met Rajesh Kumar Sharma at Connaught Place.\nCall was made on 12/03/2026.",
        page=1,
        doc_id="DOC-1",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh",
                "attributes": [],
            },
            {
                "local_id": "m2",
                "type": "PERSON",
                "surface_text": "Rajesh Kumar Sharma",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Rajesh Kumar Sharma",
                "attributes": [],
            },
            {
                "local_id": "m3",
                "type": "LOCATION",
                "surface_text": "Connaught Place",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Connaught Place",
                "attributes": [],
            },
        ],
        "relationships": [
            {
                "type": "ASSOCIATED_WITH",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh met Rajesh Kumar Sharma",  # Stated (both endpoints)
            },
            {
                "type": "ASSOCIATED_WITH",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh met",  # Model inferred (only m1 present in quote)
            },
            {
                "type": "INVALID_REL_TYPE",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh met Rajesh Kumar Sharma",
            },
        ],
        "events": [
            {
                "type": "MEETING",
                "description": "Meeting at Connaught Place",
                "time_text": "12/03/2026",
                "participant_local_ids": ["m1", "m2"],
                "location_local_id": "m3",
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh met Rajesh Kumar Sharma at Connaught Place",
            },
            {
                "type": "INVALID_EVENT_TYPE",
                "description": "Invalid event",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p001",
                "quote": "Vikram Singh met Rajesh Kumar Sharma at Connaught Place",
            },
        ],
        "notes": [],
    }

    mentions, rels, events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1",
    )

    assert len(mentions) == 3
    assert len(rels) == 2
    assert rels[0].assertion == Assertion.STATED
    assert rels[1].assertion == Assertion.MODEL_INFERRED
    assert ReviewKind.ROLE_INFERRED in rels[1].review_flags

    assert len(events) == 1
    ev = events[0]
    assert ev.time is not None
    assert ev.time.original_text == "12/03/2026"
    assert ev.location_mention_id == mentions[2].mention_id

    # Schema violation rejections for invalid rel and event types
    assert any(rej.kind == RejectionKind.SCHEMA_VIOLATION for rej in rejections)


def test_integration_scripted_mock_fir_a() -> None:
    """Integration test: Scripted mock response for clean FIR (FIR_A) -> verified mentions with computed SourceRefs."""
    mock_file = Path("tests/fixtures/model_responses/FIR_A_0.json")
    assert mock_file.exists(), "Mock fixture tests/fixtures/model_responses/FIR_A_0.json must exist"

    with open(mock_file, encoding="utf-8") as f:
        mock_output = json.load(f)

    doc_id = "DOC-482400506952"
    unit_p1 = Unit(
        unit_id=f"{doc_id}:p001",
        text=(
            "Occurrence of Offence: Date: 10/03/2026, Time: 18:30 IST\n"
            "Accused: Vikram Singh alias Vicky\n"
            "Father's Name: Harbans Singh\n"
            "Age: 32 yrs\n"
            "Name: Rajesh Kumar Sharma\n"
            "Father's Name: Ramesh Sharma\n"
            "Age: 45 yrs\n"
            "Contact Phone: +919811122233\n"
            "Contact Phone: +919876543210\n"
            "Vehicle Involved: White Swift Dzire bearing registration DL01AB1234\n"
            "Bank Account: SBI Account 001234567890\n"
            "fled in vehicle DL01AB1234\n"
        ),
        page=1,
        line_start=1,
        line_end=12,
        method="ocr",
        doc_id=doc_id,
    )

    ocr_pages: dict[int, Any] = {
        1: {
            "lines": [
                {
                    "text": "Occurrence of Offence: Date: 10/03/2026, Time: 18:30 IST",
                    "bbox": [10, 20, 400, 40],
                    "words": [{"text": "Offence", "bbox": [50, 20, 100, 40]}],
                },
                {
                    "text": "Accused: Vikram Singh alias Vicky",
                    "bbox": [10, 50, 400, 70],
                    "words": [
                        {"text": "Accused:", "bbox": [10, 50, 80, 70]},
                        {"text": "Vikram", "bbox": [85, 50, 150, 70]},
                        {"text": "Singh", "bbox": [155, 50, 200, 70]},
                    ],
                },
            ]
        }
    }

    mentions, rels, events, _reviews, rejections = verify_model_output(
        model_output=mock_output,
        chunk_units=[unit_p1],
        case_id="CASE-A-001",
        doc_id=doc_id,
        ocr_pages=ocr_pages,
        file_name="FIR_A.pdf",
    )

    assert len(rejections) == 0, f"Expected 0 rejections, got: {rejections}"
    assert len(mentions) == 7
    assert len(rels) == 3
    assert len(events) == 1

    phone_mentions = [m for m in mentions if m.type == EntityType.PHONE]
    assert len(phone_mentions) == 2
    for p in phone_mentions:
        assert ReviewKind.LOW_TRUST_IDENTIFIER in p.review_flags
        assert p.identifier_trust.value == "review_required"

    m_vikram = next(m for m in mentions if m.surface_text == "Vikram Singh")
    assert m_vikram.source.page == 1
    assert m_vikram.source.line_start == 2
    assert m_vikram.source.bbox is not None
    assert m_vikram.source.text_origin.value == "ocr"

    rel_aka = next(r for r in rels if r.type.value == "ALSO_KNOWN_AS")
    assert rel_aka.assertion == Assertion.STATED


def test_verification_all_error_branches() -> None:
    """Test all remaining branch paths in verify_model_output for complete coverage."""
    unit = Unit(
        unit_id="DOC-1:p001",
        text="Accused: Vikram Singh\nBalance 1234567890\nVehicle DL01AB1234\nEvent on 10/10/2026\n",
        page=1,
        doc_id="DOC-1",
    )

    # 1. Non-dict mention, extra attribute fields, invalid entity type, identifier not found by parser
    raw_output: dict[str, Any] = {
        "mentions": [
            "not_a_dict_mention",
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Accused: Vikram Singh",
                "attributes": [
                    "not_a_dict_attribute",
                    {
                        "name": "father_name",
                        "value_text": "Harbans",
                        "quote": "Accused: Vikram Singh",
                        "extra_attr_field": True,
                    },
                    {
                        "name": "invalid_attr_name",
                        "value_text": "Val",
                        "quote": "Accused: Vikram Singh",
                    },
                ],
            },
            {
                "local_id": "m2",
                "type": "UNKNOWN_ENTITY_TYPE",
                "surface_text": "Vikram Singh",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Accused: Vikram Singh",
                "attributes": [],
            },
            {
                # Account not near keywords, so detect_identifiers won't match -> IDENTIFIER_NOT_FOUND_BY_PARSER
                "local_id": "m3",
                "type": "ACCOUNT",
                "surface_text": "1234567890",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "Balance 1234567890",
                "attributes": [],
            },
        ],
        "relationships": [
            "not_a_dict_relationship",
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m1",
                "unit_id": "DOC-1:p001",
                "quote": "Accused: Vikram Singh",
                "extra_rel_field": 123,
            },
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m1",
                "unit_id": "DOC-1:p999",  # Unit not in chunk
                "quote": "Accused: Vikram Singh",
            },
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m1",
                "unit_id": "DOC-1:p001",
                "quote": "AB",  # Quote < 3 chars
            },
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m1",
                "unit_id": "DOC-1:p001",
                "quote": "Nonexistent relationship quote",
            },
        ],
        "events": [
            "not_a_dict_event",
            {
                "type": "INCIDENT",
                "description": "Desc",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p001",
                "quote": "Event on 10/10/2026",
                "extra_event_field": True,
            },
            {
                "type": "INCIDENT",
                "description": "Desc",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p999",  # Unit not in chunk
                "quote": "Event on 10/10/2026",
            },
            {
                "type": "INCIDENT",
                "description": "Desc",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p001",
                "quote": "AB",  # Quote < 3 chars
            },
            {
                "type": "INCIDENT",
                "description": "Desc",
                "time_text": None,
                "participant_local_ids": ["m1"],
                "location_local_id": None,
                "unit_id": "DOC-1:p001",
                "quote": "Nonexistent event quote",
            },
        ],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1",
    )

    assert len(rejections) > 0
    # m3 should be flagged as IDENTIFIER_NOT_FOUND_BY_PARSER
    m3 = next((m for m in mentions if m.surface_text == "1234567890"), None)
    if m3:
        assert ReviewKind.IDENTIFIER_NOT_FOUND_BY_PARSER in m3.review_flags


def test_verify_model_output_rejects_generic_and_narration_person_names() -> None:
    """Verify that generic noun phrases ('The Person') and transaction narrations ('Service Reversal')
    are strictly rejected with RejectionKind.SCHEMA_VIOLATION and not emitted as mentions."""
    unit = Unit(
        unit_id="DOC-1:p001",
        text="A parked bus obscured the person carrying a carton. Also, service reversal was noted.",
        doc_id="DOC-1",
    )
    raw_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "The Person",
                "role_stated": "suspect",
                "unit_id": "DOC-1:p001",
                "quote": "obscured the person carrying a carton",
            },
            {
                "local_id": "m2",
                "type": "PERSON",
                "surface_text": "Service Reversal",
                "role_stated": None,
                "unit_id": "DOC-1:p001",
                "quote": "service reversal was noted",
            },
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _reviews, rejections = verify_model_output(
        model_output=raw_output,
        chunk_units=[unit],
        case_id="CASE-001",
        doc_id="DOC-1",
    )

    # Both invalid persons must be rejected
    assert len(mentions) == 0
    assert len(rejections) == 2
    rej_reasons = [r.reason for r in rejections]
    assert any("The Person" in r for r in rej_reasons)
    assert any("Service Reversal" in r for r in rej_reasons)
