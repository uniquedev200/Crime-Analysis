"""Unit tests for ingestion file type detection and magic bytes verification.

All tests are marked @pytest.mark.gate1 and use UTF-8 encoding.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import reportlab.pdfgen.canvas as canvas
from PIL import Image

from atlas.errors import RejectedInputError
from atlas.ingest.detect import (
    REJECTED_MACRO_EXTENSIONS,
    detect_file_type,
)


def _create_minimal_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), invariant=1)
    c.drawString(100, 700, "Synthetic Gate 1 Test Document")
    c.save()
    return path


def _create_minimal_png(path: Path) -> Path:
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(str(path), format="PNG")
    return path


def _create_minimal_jpeg(path: Path) -> Path:
    img = Image.new("RGB", (10, 10), color="red")
    img.save(str(path), format="JPEG")
    return path


def _create_minimal_tiff(path: Path) -> Path:
    img = Image.new("RGB", (10, 10), color="green")
    img.save(str(path), format="TIFF")
    return path


def _create_minimal_xlsx(path: Path) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="utf-8"?><Types/>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="utf-8"?><workbook/>')
    path.write_bytes(buf.getvalue())
    return path


@pytest.mark.gate1
def test_detect_all_supported_types(tmp_path: Path) -> None:
    """Verify that all supported file types with valid magic bytes are correctly detected."""
    pdf_path = _create_minimal_pdf(tmp_path / "doc.pdf")
    assert detect_file_type(pdf_path) == "pdf"

    png_path = _create_minimal_png(tmp_path / "image.png")
    assert detect_file_type(png_path) == "png"

    jpg_path = _create_minimal_jpeg(tmp_path / "photo.jpg")
    assert detect_file_type(jpg_path) == "jpg"

    jpeg_path = _create_minimal_jpeg(tmp_path / "photo.jpeg")
    assert detect_file_type(jpeg_path) == "jpeg"

    tif_path = _create_minimal_tiff(tmp_path / "scan.tif")
    assert detect_file_type(tif_path) == "tif"

    tiff_path = _create_minimal_tiff(tmp_path / "scan.tiff")
    assert detect_file_type(tiff_path) == "tiff"

    xlsx_path = _create_minimal_xlsx(tmp_path / "data.xlsx")
    assert detect_file_type(xlsx_path) == "xlsx"

    csv_path = tmp_path / "records.csv"
    csv_path.write_text("id,name,value\n1,alpha,100\n", encoding="utf-8")
    assert detect_file_type(csv_path) == "csv"

    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("Case FIR summary notes here.\n", encoding="utf-8")
    assert detect_file_type(txt_path) == "txt"

    json_path = tmp_path / "config.json"
    json_path.write_text('{"status": "ok", "count": 1}', encoding="utf-8")
    assert detect_file_type(json_path) == "json"


@pytest.mark.gate1
@pytest.mark.parametrize("ext", sorted(REJECTED_MACRO_EXTENSIONS))
def test_reject_macro_formats(tmp_path: Path, ext: str) -> None:
    """Verify that macro/legacy formats (.xlsm, .xls, .docm) are rejected with explicit reason."""
    path = tmp_path / f"malicious.{ext}"
    path.write_bytes(b"dummy payload")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(path)
    err = str(exc_info.value).lower()
    assert ext in err
    assert "macro" in err or "legacy" in err or "unsupported" in err


@pytest.mark.gate1
@pytest.mark.parametrize("ext", ["exe", "bin", "sh", "bat", "py", "docx"])
def test_reject_unsupported_extensions(tmp_path: Path, ext: str) -> None:
    """Verify that unsupported extensions are rejected before reading file content."""
    path = tmp_path / f"test.{ext}"
    path.write_text("print('hello')", encoding="utf-8")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(path)
    assert f".{ext}" in str(exc_info.value)


@pytest.mark.gate1
def test_reject_empty_file(tmp_path: Path) -> None:
    """Empty files with 0 bytes must be rejected with explicit message."""
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(empty)
    assert "empty file" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_reject_no_extension(tmp_path: Path) -> None:
    """Files without an extension must be rejected."""
    no_ext = tmp_path / "document_no_ext"
    no_ext.write_text("some content", encoding="utf-8")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(no_ext)
    assert "no extension" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_file_not_found_raises(tmp_path: Path) -> None:
    """Non-existent file raises FileNotFoundError."""
    missing = tmp_path / "does_not_exist.pdf"
    with pytest.raises(FileNotFoundError):
        detect_file_type(missing)


@pytest.mark.gate1
def test_magic_mismatch_png_named_pdf(tmp_path: Path) -> None:
    """File containing PNG bytes but named .pdf must be rejected with mismatch reason."""
    fake_pdf = tmp_path / "fake.pdf"
    _create_minimal_png(fake_pdf)
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(fake_pdf)
    err = str(exc_info.value).lower()
    assert "magic bytes mismatch" in err or "mismatch" in err
    assert "png" in err or "pdf" in err


@pytest.mark.gate1
def test_magic_mismatch_pdf_named_png(tmp_path: Path) -> None:
    """File containing PDF bytes but named .png must be rejected."""
    fake_png = tmp_path / "fake.png"
    _create_minimal_pdf(fake_png)
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(fake_png)
    assert "magic bytes mismatch" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_magic_mismatch_binary_in_text(tmp_path: Path) -> None:
    """Text file with binary null bytes or magic header must be rejected."""
    bad_txt = tmp_path / "bad.txt"
    bad_txt.write_bytes(b"%PDF-1.4 binary data\x00\x01\x02")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(bad_txt)
    assert "magic bytes mismatch" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_magic_mismatch_invalid_json_text(tmp_path: Path) -> None:
    """JSON file that does not start with object or array must be rejected."""
    bad_json = tmp_path / "malformed.json"
    bad_json.write_text("Just plain text without json structures", encoding="utf-8")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(bad_json)
    assert "invalid json" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_magic_mismatch_corrupt_xlsx(tmp_path: Path) -> None:
    """Non-ZIP bytes named .xlsx must be rejected."""
    bad_xlsx = tmp_path / "bad.xlsx"
    bad_xlsx.write_text("Not a zip file at all", encoding="utf-8")
    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(bad_xlsx)
    assert "mismatch" in str(exc_info.value).lower() or "zip" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_detect_big_endian_tiff(tmp_path: Path) -> None:
    """TIFF with big-endian magic MM\x00* is properly detected."""
    be_tiff = tmp_path / "big_endian.tif"
    be_tiff.write_bytes(b"MM\x00*\x00\x00\x00\x08dummy tiff body")
    assert detect_file_type(be_tiff) == "tif"


@pytest.mark.gate1
def test_reject_xlsx_without_spreadsheets(tmp_path: Path) -> None:
    """ZIP file missing xl/ or [Content_Types].xml is rejected as invalid XLSX."""
    fake_xlsx = tmp_path / "not_excel.xlsx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
    fake_xlsx.write_bytes(buf.getvalue())

    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(fake_xlsx)
    assert "invalid xlsx" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_reject_non_utf8_text_file(tmp_path: Path) -> None:
    """Text file with invalid UTF-8 bytes is rejected with encoding error."""
    bad_utf8 = tmp_path / "bad_encoding.txt"
    bad_utf8.write_bytes(b"Valid ASCII \xff\xfe Invalid bytes")

    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(bad_utf8)
    assert "encoding error" in str(exc_info.value).lower() or "utf-8" in str(exc_info.value).lower()
