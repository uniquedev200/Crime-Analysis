"""JSON file extraction for ATLAS Dev 3.

Traverses JSON hierarchical structures using RFC 6901 JSON pointers,
emitting deterministic unit_ids following {doc_id}:j:{pointer}.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas.contracts.ids import make_doc_id, make_unit_id_json
from atlas.extract.units import Unit
from atlas.ingest.integrity import compute_sha256


def _escape_pointer_segment(segment: str) -> str:
    """Escape '~' as '~0' and '/' as '~1' according to RFC 6901."""
    return segment.replace("~", "~0").replace("/", "~1")


def extract_json_file(path: Path, doc_id: str | None = None) -> list[dict[str, Any]]:
    """Extract JSON file into flat list of units with RFC 6901 JSON pointers.

    Unit ID format: {doc_id}:j:{pointer}.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")

    if doc_id is None:
        file_sha = compute_sha256(path)
        doc_id = make_doc_id(file_sha)

    content = path.read_text(encoding="utf-8")
    data = json.loads(content)

    items: list[dict[str, Any]] = []

    def _traverse(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            if not node:
                ptr = pointer if pointer else "/"
                unit_id = make_unit_id_json(doc_id, ptr)
                items.append(
                    {
                        "unit_id": unit_id,
                        "pointer": ptr,
                        "text": "{}",
                        "value": {},
                        "doc_id": doc_id,
                        "method": "json_file",
                    }
                )
            else:
                for key, val in node.items():
                    sub_ptr = f"{pointer}/{_escape_pointer_segment(str(key))}"
                    _traverse(val, sub_ptr)
        elif isinstance(node, list):
            if not node:
                ptr = pointer if pointer else "/"
                unit_id = make_unit_id_json(doc_id, ptr)
                items.append(
                    {
                        "unit_id": unit_id,
                        "pointer": ptr,
                        "text": "[]",
                        "value": [],
                        "doc_id": doc_id,
                        "method": "json_file",
                    }
                )
            else:
                for idx, val in enumerate(node):
                    sub_ptr = f"{pointer}/{idx}"
                    _traverse(val, sub_ptr)
        else:
            ptr = pointer if pointer else "/value"
            unit_id = make_unit_id_json(doc_id, ptr)
            text_repr = "" if node is None else str(node)
            items.append(
                {
                    "unit_id": unit_id,
                    "pointer": ptr,
                    "text": text_repr,
                    "value": node,
                    "doc_id": doc_id,
                    "method": "json_file",
                }
            )

    _traverse(data, "")
    return items


def extract_json_file_units(path: Path, doc_id: str | None = None) -> list[Unit]:
    """Extract JSON file directly into Unit instances."""
    items = extract_json_file(path, doc_id=doc_id)
    return [
        Unit(
            unit_id=str(item["unit_id"]),
            text=str(item["text"]),
            page=None,
            line_start=None,
            line_end=None,
            method=str(item["method"]),
            doc_id=str(item["doc_id"]),
        )
        for item in items
    ]


__all__ = ["extract_json_file", "extract_json_file_units"]
