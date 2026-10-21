"""Unit data structures and creation helpers for ATLAS Dev 3 extraction.

Units represent atomic textual segments (pages, lines, rows, json fields)
with deterministic identifiers generated prior to any LLM analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atlas.contracts.ids import (
    make_unit_id_json,
    make_unit_id_line,
    make_unit_id_page,
    make_unit_id_text_line,
)


@dataclass
class Unit:
    """Atomic textual unit extracted from a document with traceable provenance."""

    unit_id: str
    text: str
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    method: str = "pdf_text"
    doc_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Convert Unit instance to dictionary."""
        return {
            "unit_id": self.unit_id,
            "text": self.text,
            "page": self.page,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "method": self.method,
            "doc_id": self.doc_id,
            "warnings": list(self.warnings),
        }


def create_page_units(
    doc_id: str,
    pages_text: list[str],
    method: str = "pdf_text",
) -> list[Unit]:
    """Create Unit instances for a sequence of document pages.

    Pages are 1-indexed. Unit IDs follow pattern {doc_id}:p{page:03d}.
    """
    units: list[Unit] = []
    for page_idx, text in enumerate(pages_text, start=1):
        unit_id = make_unit_id_page(doc_id, page_idx)
        lines = text.splitlines()
        line_count = len(lines) if lines else 1
        units.append(
            Unit(
                unit_id=unit_id,
                text=text,
                page=page_idx,
                line_start=1 if lines else None,
                line_end=line_count if lines else None,
                method=method,
                doc_id=doc_id,
            )
        )
    return units


def create_line_units(
    doc_id: str,
    page: int,
    lines: list[str],
    method: str = "pdf_text",
) -> list[Unit]:
    """Create Unit instances for lines on a specific document page.

    Lines are 1-indexed. Unit IDs follow pattern {doc_id}:p{page:03d}:l{line:03d}.
    """
    units: list[Unit] = []
    for line_idx, line_text in enumerate(lines, start=1):
        unit_id = make_unit_id_line(doc_id, page, line_idx)
        units.append(
            Unit(
                unit_id=unit_id,
                text=line_text,
                page=page,
                line_start=line_idx,
                line_end=line_idx,
                method=method,
                doc_id=doc_id,
            )
        )
    return units


def create_text_line_units(
    doc_id: str,
    lines: list[str],
    method: str = "text",
) -> list[Unit]:
    """Create Unit instances for lines in a plain text file.

    Lines are 1-indexed. Unit IDs follow pattern {doc_id}:l{line:06d}.
    """
    units: list[Unit] = []
    for line_idx, line_text in enumerate(lines, start=1):
        unit_id = make_unit_id_text_line(doc_id, line_idx)
        units.append(
            Unit(
                unit_id=unit_id,
                text=line_text,
                page=None,
                line_start=line_idx,
                line_end=line_idx,
                method=method,
                doc_id=doc_id,
            )
        )
    return units


def create_json_pointer_unit(
    doc_id: str,
    pointer: str,
    text: str,
    method: str = "json",
) -> Unit:
    """Create a Unit instance for a JSON pointer location."""
    unit_id = make_unit_id_json(doc_id, pointer)
    return Unit(
        unit_id=unit_id,
        text=text,
        page=None,
        line_start=None,
        line_end=None,
        method=method,
        doc_id=doc_id,
    )


__all__ = [
    "Unit",
    "create_json_pointer_unit",
    "create_line_units",
    "create_page_units",
    "create_text_line_units",
]
