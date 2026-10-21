"""Unit tests for contradiction detection across clustered mentions.

Tests verify Section 5.6 requirements:
- Age diff > 2 years -> contradiction review item with all sources
- Age diff <= 2 years -> no contradiction
- Father name diff -> contradiction review item with all sources
- Both conflicting values preserved (never picked or suppressed)
"""

from __future__ import annotations

import pytest

from atlas.consolidate.contradictions import detect_contradictions, extract_numeric_age
from atlas.contracts.enums import AttrName, EntityType, Origin, QuoteStatus, ReviewKind, UnitKind
from atlas.contracts.records import Mention, MentionAttribute, SourceRef

pytestmark = pytest.mark.gate2


def _make_source(unit_id: str, quote: str) -> SourceRef:
    return SourceRef(
        doc_id="DOC-1234567890ab",
        file_name="fir.pdf",
        file_sha256="1234567890abcdef" * 4,
        unit_id=unit_id,
        unit_kind=UnitKind.PAGE,
        page=1,
        line_start=1,
        line_end=1,
        bbox=None,
        text_origin=Origin.PDF_TEXT,
        quote=quote,
        quote_status=QuoteStatus.VERIFIED,
        occurrence_count=1,
    )


def test_extract_numeric_age() -> None:
    """Helper extract_numeric_age parses various age strings."""
    assert extract_numeric_age("32") == 32
    assert extract_numeric_age("32 yrs") == 32
    assert extract_numeric_age("Age: 45 years") == 45
    assert extract_numeric_age("unknown") is None


def test_age_diff_greater_than_2_years_emits_contradiction() -> None:
    """Age difference > 2 years emits contradiction ReviewItem holding all conflicting values and sources."""
    s1 = _make_source("DOC-123:p001", "Age: 32 yrs")
    s2 = _make_source("DOC-123:p002", "Age: 45 yrs")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.AGE, value_text="32 yrs", source=s1)],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.AGE, value_text="45 yrs", source=s2)],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    items = detect_contradictions([m1, m2], case_id="CASE-001")

    assert len(items) == 1
    item = items[0]
    assert item.kind == ReviewKind.CONTRADICTION
    # Conflicting values preserved in detail
    assert "32 yrs" in item.detail
    assert "45 yrs" in item.detail
    # Both sources preserved in detail
    assert "Age: 32 yrs" in item.detail
    assert "Age: 45 yrs" in item.detail
    assert set(item.target_ids) == {"M-001", "M-002"}


def test_age_diff_within_2_years_tolerance_no_contradiction() -> None:
    """Age difference <= 2 years (e.g. 32 vs 34, diff=2) is tolerated and does not emit contradiction."""
    s1 = _make_source("DOC-123:p001", "Age: 32 yrs")
    s2 = _make_source("DOC-123:p002", "Age: 34 yrs")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.AGE, value_text="32 yrs", source=s1)],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.AGE, value_text="34 yrs", source=s2)],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    items = detect_contradictions([m1, m2], case_id="CASE-001")
    assert len(items) == 0


def test_father_name_diff_emits_contradiction_with_sources() -> None:
    """Differing father_name attributes emit contradiction ReviewItem with all values and sources."""
    s1 = _make_source("DOC-123:p001", "Father's Name: Harbans Singh")
    s2 = _make_source("DOC-123:p002", "Father's Name: Ramesh Sharma")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.FATHER_NAME, value_text="Harbans Singh", source=s1)],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.FATHER_NAME, value_text="Ramesh Sharma", source=s2)],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    items = detect_contradictions([m1, m2], case_id="CASE-001")

    assert len(items) == 1
    item = items[0]
    assert item.kind == ReviewKind.CONTRADICTION
    # Both conflicting values preserved
    assert "Harbans Singh" in item.detail
    assert "Ramesh Sharma" in item.detail
    # Both sources preserved
    assert "Father's Name: Harbans Singh" in item.detail
    assert "Father's Name: Ramesh Sharma" in item.detail


def test_dob_diff_emits_contradiction() -> None:
    """Differing DOB values emit contradiction ReviewItem preserving all values and sources."""
    s1 = _make_source("DOC-123:p001", "DOB: 15/08/1990")
    s2 = _make_source("DOC-123:p002", "DOB: 20/12/1988")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.DOB, value_text="15/08/1990", source=s1)],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-123",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.DOB, value_text="20/12/1988", source=s2)],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    items = detect_contradictions([m1, m2], case_id="CASE-001")
    assert len(items) == 1
    assert "15/08/1990" in items[0].detail
    assert "20/12/1988" in items[0].detail
