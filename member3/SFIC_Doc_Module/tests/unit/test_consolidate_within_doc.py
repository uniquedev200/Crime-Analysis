"""Unit tests for within-document consolidation and person clustering.

Tests verify Section 5.6 requirements:
- Chunk deduplication merges sources
- Same person identical name_key merged
- Stated ALSO_KNOWN_AS merges alias
- Same name with different father_name stays separate
"""

from __future__ import annotations

import pytest

from atlas.consolidate.within_doc import (
    cluster_persons_within_doc,
    consolidate_within_doc,
    deduplicate_mentions,
)
from atlas.contracts.enums import (
    Assertion,
    AttrName,
    EntityType,
    EventType,
    Origin,
    QuoteStatus,
    RelType,
    UnitKind,
)
from atlas.contracts.records import (
    Event,
    Mention,
    MentionAttribute,
    Relationship,
    SourceRef,
)

pytestmark = pytest.mark.gate2


def _make_sample_source(unit_id: str, quote: str, occurrence_count: int = 1) -> SourceRef:
    return SourceRef(
        doc_id="DOC-1234567890ab",
        file_name="sample.pdf",
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
        occurrence_count=occurrence_count,
    )


def test_chunk_deduplication_merges_sources() -> None:
    """Mentions duplicated across chunks are deduplicated and their occurrence counts are merged."""
    s1 = _make_sample_source("DOC-1234567890ab:p001", "Accused: Vikram Singh", occurrence_count=1)
    s2 = _make_sample_source("DOC-1234567890ab:p001", "Accused: Vikram Singh", occurrence_count=1)

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="Vikram Singh",
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="Vikram Singh",
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    deduped = deduplicate_mentions([m1, m2])
    assert len(deduped) == 1
    # Sources merged: occurrence_count is now 1 + 1 = 2
    assert deduped[0].source.occurrence_count == 2


def test_same_person_identical_name_key_merged() -> None:
    """Mentions of the same person with identical name_key and compatible attributes merge into one cluster."""
    s1 = _make_sample_source("DOC-1234567890ab:p001", "Shri Vikram Singh")
    s2 = _make_sample_source("DOC-1234567890ab:p002", "Vikram Singh")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Shri Vikram Singh",
        normalized_value="Vikram Singh",
        attributes=[
            MentionAttribute(name=AttrName.AGE, value_text="32"),
            MentionAttribute(name=AttrName.FATHER_NAME, value_text="Harbans Singh"),
        ],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        normalized_value="Vikram Singh",
        attributes=[
            MentionAttribute(name=AttrName.AGE, value_text="33"),  # Within +/- 2 years tolerance
            MentionAttribute(name=AttrName.FATHER_NAME, value_text="Harbans Singh"),
        ],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    clusters, review_items = cluster_persons_within_doc(
        mentions=[m1, m2],
        relationships=[],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(clusters) == 1
    cluster = clusters[0]
    assert set(cluster.mention_ids) == {"M-001", "M-002"}
    assert len(cluster.mentions) == 2
    # All sources preserved
    assert len(cluster.sources) == 2
    assert len(review_items) == 0


def test_stated_also_known_as_merges_alias() -> None:
    """Stated ALSO_KNOWN_AS relationship links alias form (e.g. 'Vicky') to primary person."""
    s1 = _make_sample_source("DOC-1234567890ab:p001", "Accused Vikram Singh alias Vicky")
    s2 = _make_sample_source("DOC-1234567890ab:p001", "Accused Vikram Singh alias Vicky")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vicky",
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    rel = Relationship(
        rel_id="R-001",
        case_id="CASE-001",
        type=RelType.ALSO_KNOWN_AS,
        subject_mention_id="M-001",
        object_mention_id="M-002",
        assertion=Assertion.STATED,
        origin=Origin.PDF_TEXT,
        source=s1,
    )

    clusters, _review_items = cluster_persons_within_doc(
        mentions=[m1, m2],
        relationships=[rel],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(clusters) == 1
    assert set(clusters[0].mention_ids) == {"M-001", "M-002"}


def test_same_name_with_different_father_name_stays_separate() -> None:
    """Two mentions with identical name but differing father_name stay separate as distinct clusters."""
    s1 = _make_sample_source("DOC-1234567890ab:p001", "Vikram Singh S/o Harbans Singh")
    s2 = _make_sample_source("DOC-1234567890ab:p002", "Vikram Singh S/o Ramesh Singh")

    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.FATHER_NAME, value_text="Harbans Singh")],
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    m2 = Mention(
        mention_id="M-002",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        attributes=[MentionAttribute(name=AttrName.FATHER_NAME, value_text="Ramesh Singh")],
        origin=Origin.PDF_TEXT,
        source=s2,
    )

    clusters, _review_items = cluster_persons_within_doc(
        mentions=[m1, m2],
        relationships=[],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    # Must NOT merge into one cluster; must stay separate!
    assert len(clusters) == 2
    assert {clusters[0].mention_ids[0], clusters[1].mention_ids[0]} == {"M-001", "M-002"}


def test_consolidate_within_doc_end_to_end() -> None:
    """Full consolidate_within_doc pipeline deduplicates items and clusters persons."""
    s1 = _make_sample_source("DOC-1234567890ab:p001", "Accused: Vikram Singh")
    m1 = Mention(
        mention_id="M-001",
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
        type=EntityType.PERSON,
        surface_text="Vikram Singh",
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    rel1 = Relationship(
        rel_id="R-001",
        case_id="CASE-001",
        type=RelType.ASSOCIATED_WITH,
        subject_mention_id="M-001",
        object_mention_id="M-001",
        assertion=Assertion.STATED,
        origin=Origin.PDF_TEXT,
        source=s1,
    )
    ev1 = Event(
        event_id="E-001",
        case_id="CASE-001",
        type=EventType.INCIDENT,
        description="Incident report",
        origin=Origin.PDF_TEXT,
        source=s1,
    )

    d_m, d_r, d_e, clusters, _reviews = consolidate_within_doc(
        mentions=[m1],
        relationships=[rel1],
        events=[ev1],
        case_id="CASE-001",
        doc_id="DOC-1234567890ab",
    )

    assert len(d_m) == 1
    assert len(d_r) == 1
    assert len(d_e) == 1
    assert len(clusters) == 1
