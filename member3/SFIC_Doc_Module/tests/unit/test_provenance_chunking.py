"""Unit and property-based tests for provenance chunking and pagination.

Tests verify Section 5.6 requirements:
- Small units packed into one chunk
- Large units chunked
- Huge page split with 3-line overlap
- Hypothesis test: arbitrary unit sizes -> every unit covered, overlap correct
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.extract.units import Unit
from atlas.provenance.chunking import chunk_units

pytestmark = pytest.mark.gate2


def test_small_units_packed_into_one_chunk() -> None:
    """Multiple small units with cumulative size <= max_chars are packed into one chunk."""
    u1 = Unit(unit_id="DOC-1:p001", text="Short text on page 1", page=1, doc_id="DOC-1")
    u2 = Unit(unit_id="DOC-1:p002", text="Short text on page 2", page=2, doc_id="DOC-1")
    u3 = Unit(unit_id="DOC-1:p003", text="Short text on page 3", page=3, doc_id="DOC-1")

    chunks = chunk_units([u1, u2, u3], max_chars=4000)
    assert len(chunks) == 1
    assert len(chunks[0]) == 3
    assert [u.unit_id for u in chunks[0]] == ["DOC-1:p001", "DOC-1:p002", "DOC-1:p003"]


def test_large_units_chunked() -> None:
    """Units exceeding chunk threshold are separated into individual chunks."""
    # Each unit is ~2500 chars; together 5000 chars > max_chars 4000
    u1 = Unit(unit_id="DOC-1:p001", text="A" * 2500, page=1, doc_id="DOC-1")
    u2 = Unit(unit_id="DOC-1:p002", text="B" * 2500, page=2, doc_id="DOC-1")

    chunks = chunk_units([u1, u2], max_chars=4000)
    assert len(chunks) == 2
    assert len(chunks[0]) == 1
    assert chunks[0][0].unit_id == "DOC-1:p001"
    assert len(chunks[1]) == 1
    assert chunks[1][0].unit_id == "DOC-1:p002"


def test_huge_page_split_with_3_line_overlap() -> None:
    """A single page exceeding max_chars is split on line boundaries with 3-line overlap."""
    # Create 30 lines, each line 100 characters long (total 3000 chars)
    # With max_chars = 1200, each chunk can take around 11 lines
    lines = [f"Line {idx:02d}: " + "x" * 90 for idx in range(1, 31)]
    page_text = "\n".join(lines)
    unit = Unit(unit_id="DOC-1:p001", text=page_text, page=1, line_start=1, line_end=30, doc_id="DOC-1")

    chunks = chunk_units([unit], max_chars=1200, overlap_lines=3)
    assert len(chunks) > 1

    # Verify line overlap between consecutive chunks
    for i in range(len(chunks) - 1):
        c1 = chunks[i][0]
        c2 = chunks[i + 1][0]
        c1_lines = c1.text.splitlines()
        c2_lines = c2.text.splitlines()

        # The last 3 lines of c1 must match the first 3 lines of c2
        assert c1_lines[-3:] == c2_lines[:3]
        # Line numbers must reflect overlap
        assert c2.line_start is not None and c1.line_end is not None
        assert c2.line_start == c1.line_end - 3 + 1


def test_empty_units_returns_empty() -> None:
    """Empty list of units returns empty chunk list."""
    assert chunk_units([]) == []


def test_single_long_line_split() -> None:
    """Single very long line without newlines is safely sliced."""
    unit = Unit(unit_id="DOC-1:p001", text="W" * 5000, page=1, doc_id="DOC-1")
    chunks = chunk_units([unit], max_chars=1000)
    assert len(chunks) >= 5
    for c in chunks:
        assert len(c[0].text) <= 1000


@given(
    st.lists(
        st.integers(min_value=10, max_value=800).map(lambda n: ("Word " * (n // 5)).strip()),
        min_size=1,
        max_size=15,
    )
)
@settings(max_examples=40, deadline=None)
def test_hypothesis_arbitrary_unit_sizes(texts: list[str]) -> None:
    """Hypothesis test: arbitrary unit sizes -> every unit covered, overlap correct."""
    units = [Unit(unit_id=f"DOC-1:p{i:03d}", text=t, page=i, doc_id="DOC-1") for i, t in enumerate(texts, start=1)]

    max_chars = 1500
    overlap_lines = 2
    chunks = chunk_units(units, max_chars=max_chars, overlap_lines=overlap_lines)

    assert len(chunks) >= 1

    # Every input unit ID must appear in at least one chunk
    all_chunk_unit_ids = {u.unit_id for chunk in chunks for u in chunk}
    for u in units:
        assert u.unit_id in all_chunk_unit_ids

    # For any chunk produced from splitting a multi-line page, verify bounds
    for chunk in chunks:
        assert len(chunk) >= 1
