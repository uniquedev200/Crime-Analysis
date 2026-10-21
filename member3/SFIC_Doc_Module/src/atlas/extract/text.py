"""Plain text file extraction for ATLAS Dev 3.

Processes UTF-8 text files line-by-line, assigning deterministic unit_ids
following the schema {doc_id}:l{line:06d}.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.contracts.ids import make_doc_id, make_unit_id_text_line
from atlas.extract.units import Unit
from atlas.ingest.integrity import compute_sha256


def extract_text_file(path: Path, doc_id: str | None = None) -> list[dict[str, Any]]:
    """Extract plain text file line-by-line with deterministic unit_ids.

    Unit ID format: {doc_id}:l{line:06d}.
    Line numbers are 1-indexed.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Text file not found: {path}")

    if doc_id is None:
        file_sha = compute_sha256(path)
        doc_id = make_doc_id(file_sha)

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    units_data: list[dict[str, Any]] = []
    for line_idx, line_text in enumerate(lines, start=1):
        unit_id = make_unit_id_text_line(doc_id, line_idx)
        units_data.append(
            {
                "unit_id": unit_id,
                "text": line_text,
                "line": line_idx,
                "line_start": line_idx,
                "line_end": line_idx,
                "doc_id": doc_id,
                "method": "text_file",
            }
        )

    return units_data


def extract_text_file_units(path: Path, doc_id: str | None = None) -> list[Unit]:
    """Extract plain text file directly into Unit instances."""
    items = extract_text_file(path, doc_id=doc_id)
    return [
        Unit(
            unit_id=str(item["unit_id"]),
            text=str(item["text"]),
            page=None,
            line_start=int(item["line_start"]),
            line_end=int(item["line_end"]),
            method=str(item["method"]),
            doc_id=str(item["doc_id"]),
        )
        for item in items
    ]


__all__ = ["extract_text_file", "extract_text_file_units"]
