"""Gate 2 unit tests for model-reported unit_id resolution in provenance verification.

Live providers sometimes echo only the trailing segment of the ``[UNIT ...]`` header
(for example ``l000005`` instead of ``DOC-ab12cd34ef56:p001:l000005``). These tests
lock in deterministic, non-inventing resolution against the units actually shown to
the model, and confirm ambiguous or foreign references are still rejected.
"""

from __future__ import annotations

import pytest

from atlas.contracts.enums import EntityType, RejectionKind, StatedRole
from atlas.extract.units import Unit
from atlas.provenance.verify import resolve_unit_id, verify_model_output

pytestmark = pytest.mark.gate2


def _unit(unit_id: str, text: str, doc_id: str, page: int | None = None, line: int | None = None) -> Unit:
    return Unit(
        unit_id=unit_id,
        text=text,
        page=page,
        line_start=line,
        line_end=line,
        method="text",
        doc_id=doc_id,
    )


def test_resolve_exact_and_unique_suffix() -> None:
    """An exact id and a unique trailing-segment reference both resolve."""
    units = [
        _unit("DOC-abc:l000001", "alpha", "DOC-abc", line=1),
        _unit("DOC-abc:l000002", "beta", "DOC-abc", line=2),
    ]
    by_id = {u.unit_id: u for u in units}

    assert resolve_unit_id("DOC-abc:l000001", by_id, "DOC-abc") == "DOC-abc:l000001"
    assert resolve_unit_id("l000002", by_id, "DOC-abc") == "DOC-abc:l000002"
    assert resolve_unit_id("DOC-abc:p001:l000002", by_id, "DOC-abc") is None  # not a suffix of any unit


def test_resolve_rejects_ambiguous_and_foreign() -> None:
    """Ambiguous, unknown or foreign-document references are refused, never guessed."""
    ambiguous = [
        _unit("DOC-abc:p001:l000001", "one", "DOC-abc", page=1, line=1),
        _unit("DOC-abc:p002:l000001", "two", "DOC-abc", page=2, line=1),
    ]
    by_id = {u.unit_id: u for u in ambiguous}

    assert resolve_unit_id("l000001", by_id, "DOC-abc") is None
    assert resolve_unit_id("l999999", by_id, "DOC-abc") is None

    foreign = {u.unit_id: u for u in [_unit("DOC-zzz:l000001", "other", "DOC-zzz", line=1)]}
    assert resolve_unit_id("l000001", foreign, "DOC-abc") is None


def test_verify_accepts_abbreviated_unit_ids_without_inventing() -> None:
    """Mentions/relationships with abbreviated unit ids verify and keep real provenance."""
    doc_id = "DOC-abc"
    units = [
        _unit("DOC-abc:l000001", "Vikram Singh was present at the scene.", doc_id, line=1),
        _unit("DOC-abc:l000002", "He was operating mobile number +919876543210.", doc_id, line=2),
    ]
    model_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "unknown",
                "unit_id": "l000001",
                "quote": "Vikram Singh was present",
                "attributes": [],
            },
            {
                "local_id": "m2",
                "type": "PHONE",
                "surface_text": "+919876543210",
                "role_stated": "unknown",
                "unit_id": "DOC-abc:l000002",
                "quote": "mobile number +919876543210",
                "attributes": [],
            },
        ],
        "relationships": [
            {
                "type": "USES_PHONE",
                "subject_local_id": "m1",
                "object_local_id": "m2",
                "unit_id": "l000002",
                "quote": "mobile number +919876543210",
            }
        ],
        "events": [],
        "notes": [],
    }

    mentions, relationships, _events, _review, rejections = verify_model_output(
        model_output=model_output,
        chunk_units=units,
        case_id="CASE-A-001",
        doc_id=doc_id,
        file_name="note.txt",
        file_sha256="a" * 64,
    )

    unit_rejections = [r for r in rejections if r.kind == RejectionKind.UNIT_NOT_IN_CHUNK]
    assert unit_rejections == [], unit_rejections

    person = next(m for m in mentions if m.type == EntityType.PERSON)
    assert person.stated_role == StatedRole.UNKNOWN
    # Provenance is computed from the real unit the reference resolved to.
    assert person.source.unit_id == "DOC-abc:l000001"
    assert person.source.line_start == 1

    assert len(relationships) == 1
    assert relationships[0].source.unit_id == "DOC-abc:l000002"


def test_verify_still_rejects_unknown_unit_id() -> None:
    """A reference that matches no chunk unit is rejected as before."""
    doc_id = "DOC-abc"
    units = [_unit("DOC-abc:l000001", "Vikram Singh was present.", doc_id, line=1)]
    model_output = {
        "mentions": [
            {
                "local_id": "m1",
                "type": "PERSON",
                "surface_text": "Vikram Singh",
                "role_stated": "unknown",
                "unit_id": "l000999",
                "quote": "Vikram Singh was present",
                "attributes": [],
            }
        ],
        "relationships": [],
        "events": [],
        "notes": [],
    }

    mentions, _rels, _events, _review, rejections = verify_model_output(
        model_output=model_output,
        chunk_units=units,
        case_id="CASE-A-001",
        doc_id=doc_id,
    )

    assert mentions == []
    assert any(r.kind == RejectionKind.UNIT_NOT_IN_CHUNK for r in rejections)
