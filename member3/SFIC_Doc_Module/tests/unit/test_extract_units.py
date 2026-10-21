"""Unit tests for unit generation, text file extraction, JSON file extraction, and image extraction.

All tests are marked @pytest.mark.gate1 and use UTF-8 encoding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from atlas.errors import RejectedInputError
from atlas.extract.image import extract_from_image
from atlas.extract.jsonfile import extract_json_file, extract_json_file_units
from atlas.extract.text import extract_text_file, extract_text_file_units
from atlas.extract.units import (
    Unit,
    create_json_pointer_unit,
    create_line_units,
    create_page_units,
    create_text_line_units,
)


class DummyImageOcrEngine:
    """Mock OCR engine for image extraction testing."""

    def __init__(self, text: str = "OCR Text Line 1\nOCR Text Line 2") -> None:
        self.text = text
        self.engine_name = "dummy_image_ocr"
        self.engine_version = "1.0.0"

    def recognize(self, image: Any, langs: list[str]) -> Any:
        return {
            "text": self.text,
            "raw_text": self.text,
            "lines": [{"text": line} for line in self.text.splitlines()],
        }


@pytest.mark.gate1
def test_unit_dataclass_fields() -> None:
    """Unit dataclass instantiates with required and optional fields."""
    u = Unit(
        unit_id="DOC-TEST:p001",
        text="Sample page text",
        page=1,
        line_start=1,
        line_end=5,
        method="pdf_text",
        doc_id="DOC-TEST",
    )
    assert u.unit_id == "DOC-TEST:p001"
    assert u.text == "Sample page text"
    assert u.page == 1
    assert u.line_start == 1
    assert u.line_end == 5
    assert u.method == "pdf_text"
    assert u.doc_id == "DOC-TEST"

    d = u.to_dict()
    assert d["unit_id"] == "DOC-TEST:p001"
    assert d["page"] == 1


@pytest.mark.gate1
def test_create_page_units_and_line_units() -> None:
    """create_page_units and create_line_units generate deterministic unit IDs."""
    doc_id = "DOC-ABC123456789"
    pages = [
        "First page content with two lines.\nSecond line here.",
        "Second page content with one line.",
    ]

    page_units = create_page_units(doc_id, pages)
    assert len(page_units) == 2

    assert page_units[0].unit_id == f"{doc_id}:p001"
    assert page_units[0].page == 1
    assert page_units[0].line_start == 1
    assert page_units[0].line_end == 2

    assert page_units[1].unit_id == f"{doc_id}:p002"
    assert page_units[1].page == 2

    # Line units for page 1
    lines = pages[0].splitlines()
    line_units = create_line_units(doc_id, page=1, lines=lines)
    assert len(line_units) == 2
    assert line_units[0].unit_id == f"{doc_id}:p001:l001"
    assert line_units[1].unit_id == f"{doc_id}:p001:l002"


@pytest.mark.gate1
def test_unit_ids_stable_across_runs() -> None:
    """Unit IDs must remain 100% deterministic and identical across repeated runs."""
    doc_id = "DOC-STABILITY01"
    sample_pages = ["Line 1\nLine 2", "Page 2 content"]

    run1_units = [u.unit_id for u in create_page_units(doc_id, sample_pages)]
    run2_units = [u.unit_id for u in create_page_units(doc_id, sample_pages)]
    assert run1_units == run2_units
    assert run1_units == [f"{doc_id}:p001", f"{doc_id}:p002"]

    lines = ["Text file line alpha", "Text file line beta"]
    run1_lines = [u.unit_id for u in create_text_line_units(doc_id, lines)]
    run2_lines = [u.unit_id for u in create_text_line_units(doc_id, lines)]
    assert run1_lines == run2_lines
    assert run1_lines == [f"{doc_id}:l000001", f"{doc_id}:l000002"]


@pytest.mark.gate1
def test_extract_text_file(tmp_path: Path) -> None:
    """extract_text_file produces line-by-line units matching {doc_id}:l{line:06d}."""
    txt_path = tmp_path / "statement.txt"
    lines = ["First statement line.", "Second statement line.", "Third statement line."]
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    doc_id = "DOC-TXT001"
    extracted = extract_text_file(txt_path, doc_id=doc_id)

    assert len(extracted) == 3
    assert extracted[0]["unit_id"] == f"{doc_id}:l000001"
    assert extracted[0]["text"] == "First statement line."
    assert extracted[0]["line"] == 1
    assert extracted[0]["method"] == "text_file"

    assert extracted[1]["unit_id"] == f"{doc_id}:l000002"
    assert extracted[2]["unit_id"] == f"{doc_id}:l000003"

    units = extract_text_file_units(txt_path, doc_id=doc_id)
    assert len(units) == 3
    assert all(isinstance(u, Unit) for u in units)


@pytest.mark.gate1
def test_extract_json_file(tmp_path: Path) -> None:
    """extract_json_file produces RFC 6901 JSON pointer units matching {doc_id}:j:{pointer}."""
    json_path = tmp_path / "evidence.json"
    data = {
        "case_name": "Operation Titan",
        "suspects": [
            {"name": "Vikram", "phone": "+919876543210"},
            {"name": "Anil", "phone": "+919876543211"},
        ],
        "metadata": {
            "version": 1,
            "tags": ["cyber", "financial"],
        },
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")

    doc_id = "DOC-JSON001"
    extracted = extract_json_file(json_path, doc_id=doc_id)

    # Pointers should include case_name, suspects/0/name, suspects/0/phone, etc.
    pointers = [item["pointer"] for item in extracted]
    assert "/case_name" in pointers
    assert "/suspects/0/name" in pointers
    assert "/suspects/0/phone" in pointers
    assert "/suspects/1/name" in pointers
    assert "/metadata/version" in pointers
    assert "/metadata/tags/0" in pointers

    # Check unit_id format
    suspect_unit = next(item for item in extracted if item["pointer"] == "/suspects/0/name")
    assert suspect_unit["unit_id"] == f"{doc_id}:j:suspects/0/name"
    assert suspect_unit["text"] == "Vikram"
    assert suspect_unit["value"] == "Vikram"

    units = extract_json_file_units(json_path, doc_id=doc_id)
    assert len(units) == len(extracted)
    assert all(isinstance(u, Unit) for u in units)


@pytest.mark.gate1
def test_extract_from_image(tmp_path: Path) -> None:
    """extract_from_image loads PIL Image and calls injected OCR engine."""
    img_path = tmp_path / "scan.png"
    img = Image.new("RGB", (100, 100), color="white")
    img.save(str(img_path))

    ocr_engine = DummyImageOcrEngine(text="FIR Scanned Evidence line 1\nOfficer remarks line 2")
    res = extract_from_image(img_path, ocr_engine=ocr_engine, langs=["eng"])

    assert res["method"] == "image_ocr"
    assert "FIR Scanned Evidence" in res["text"]
    assert len(res["lines"]) == 2
    assert res["engine"] == "dummy_image_ocr"
    assert res["path"] == str(img_path)


@pytest.mark.gate1
def test_create_json_pointer_unit_helper() -> None:
    """create_json_pointer_unit correctly formats unit_id and fields."""
    u = create_json_pointer_unit("DOC-99", "records/0/amount", "50000")
    assert u.unit_id == "DOC-99:j:records/0/amount"
    assert u.text == "50000"
    assert u.method == "json"


@pytest.mark.gate1
def test_extract_text_file_auto_doc_id(tmp_path: Path) -> None:
    """extract_text_file computes deterministic doc_id from file SHA-256 when doc_id is None."""
    txt_path = tmp_path / "autoid.txt"
    txt_path.write_text("Autonomous doc_id line.\n", encoding="utf-8")

    extracted = extract_text_file(txt_path)
    assert len(extracted) == 1
    assert extracted[0]["unit_id"].startswith("DOC-")
    assert extracted[0]["doc_id"].startswith("DOC-")


@pytest.mark.gate1
def test_extract_json_file_empty_structures(tmp_path: Path) -> None:
    """extract_json_file gracefully processes empty objects and empty arrays."""
    json_path = tmp_path / "empty_structs.json"
    data: dict[str, Any] = {"empty_obj": {}, "empty_arr": []}
    json_path.write_text(json.dumps(data), encoding="utf-8")

    extracted = extract_json_file(json_path)
    assert len(extracted) == 2
    pointers = [item["pointer"] for item in extracted]
    assert "/empty_obj" in pointers
    assert "/empty_arr" in pointers


@pytest.mark.gate1
def test_extract_from_image_edge_cases(tmp_path: Path) -> None:
    """extract_from_image enforces argument validation and handles string OCR results."""
    img_path = tmp_path / "edge.png"
    Image.new("RGB", (20, 20), color="red").save(str(img_path))

    # None ocr_engine raises ValueError
    with pytest.raises(ValueError):
        extract_from_image(img_path, ocr_engine=None)

    # Missing file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        extract_from_image(tmp_path / "missing.png", ocr_engine=DummyImageOcrEngine())

    # String OCR return value
    class StringOcrEngine:
        engine_name = "str_ocr"

        def recognize(self, img: Any, langs: list[str]) -> str:
            return "Simple raw string result"

    res = extract_from_image(img_path, ocr_engine=StringOcrEngine())
    assert res["text"] == "Simple raw string result"
    assert res["lines"] == ["Simple raw string result"]

    # Object OCR return value with lines
    class ObjLine:
        def __init__(self, text: str) -> None:
            self.text = text

    class ObjOcrResult:
        def __init__(self) -> None:
            self.raw_text = "Object text line 1\nObject line 2"
            self.lines = [ObjLine("Object text line 1"), ObjLine("Object line 2")]

    class ObjOcrEngine:
        engine_name = "obj_ocr"

        def recognize(self, img: Any, langs: list[str]) -> Any:
            return ObjOcrResult()

    res_obj = extract_from_image(img_path, ocr_engine=ObjOcrEngine())
    assert res_obj["text"] == "Object text line 1\nObject line 2"
    assert len(res_obj["lines"]) == 2

    # Corrupt image file raises RejectedInputError
    corrupt_img = tmp_path / "corrupt.png"
    corrupt_img.write_bytes(b"\x89PNG\r\n\x1a\ncorrupted data")

    with pytest.raises(RejectedInputError):
        extract_from_image(corrupt_img, ocr_engine=DummyImageOcrEngine())
