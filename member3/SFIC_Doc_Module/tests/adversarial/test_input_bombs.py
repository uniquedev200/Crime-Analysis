"""Adversarial test suite: Input bomb defense and malformed file rejection.

Tests coverage:
1. Password-protected / encrypted PDF -> rejected with RejectedInputError / rejected_input.
2. File size exceeding MAX_FILE_MB -> rejected with RejectedInputError / rejected_input.
3. Decompression-bomb-like image / pixel count exceeding MAX_IMAGE_PIXELS -> rejected with RejectedInputError / rejected_input.
4. Corrupt / truncated files (truncated PDF, corrupt XLSX, empty file, non-UTF8 text) -> rejected with RejectedInputError / rejected_input.
5. Macro-enabled formats (.xlsm, .xls, .docm) explicitly rejected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

from atlas.contracts.enums import JobState
from atlas.errors import RejectedInputError
from atlas.ingest.detect import detect_file_type
from atlas.ingest.limits import check_file_size, check_image_pixels, check_pdf_pages
from atlas.pipeline.jobs import compute_job_state

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
def test_password_protected_encrypted_pdf_rejected(tmp_path: Path) -> None:
    """Password-protected or encrypted PDF must be rejected with RejectedInputError."""
    encrypted_pdf_path = tmp_path / "encrypted_sample.pdf"

    # Generate an encrypted PDF with ReportLab
    enc = StandardEncryption("secret_password")
    c = canvas.Canvas(str(encrypted_pdf_path), encrypt=enc)
    c.drawString(100, 100, "Confidential case information")
    c.save()

    # check_pdf_pages must reject encrypted PDF
    with pytest.raises(RejectedInputError) as exc_info:
        check_pdf_pages(encrypted_pdf_path, max_pages=100)

    assert "encrypted or password-protected" in str(exc_info.value).lower()

    # Job state with input refused must evaluate to rejected_input
    job_state = compute_job_state(input_refused=True)
    assert job_state == JobState.REJECTED_INPUT
    assert job_state.value == "rejected_input"


@pytest.mark.gate5
def test_file_size_exceeding_max_file_mb_rejected(tmp_path: Path) -> None:
    """File exceeding the MAX_FILE_MB limit must be rejected immediately."""
    large_file = tmp_path / "oversized.pdf"
    # Create 2.1 MB file
    target_bytes = int(2.1 * 1024 * 1024)
    large_file.write_bytes(b"%PDF-1.4\n" + b"0" * (target_bytes - 9))

    # check_file_size with max_mb=2
    with pytest.raises(RejectedInputError) as exc_info:
        check_file_size(large_file, max_mb=2)

    assert "exceeds maximum allowed limit" in str(exc_info.value).lower()

    job_state = compute_job_state(input_refused=True)
    assert job_state == JobState.REJECTED_INPUT


@pytest.mark.gate5
def test_decompression_bomb_image_rejected(tmp_path: Path) -> None:
    """Image with pixel count exceeding MAX_IMAGE_PIXELS must be rejected as potential decompression bomb."""
    bomb_img_path = tmp_path / "huge_dimensions.png"

    # Create image with 200x200 = 40,000 pixels
    img = Image.new("RGB", (200, 200), color="red")
    img.save(bomb_img_path)

    # Set threshold strictly below image size (e.g. 5,000 pixels)
    with pytest.raises(RejectedInputError) as exc_info:
        check_image_pixels(bomb_img_path, max_pixels=5000)

    err_msg = str(exc_info.value).lower()
    assert "decompression bomb" in err_msg or "exceeds" in err_msg

    job_state = compute_job_state(input_refused=True)
    assert job_state == JobState.REJECTED_INPUT


@pytest.mark.gate5
def test_corrupt_truncated_pdf_rejected(tmp_path: Path) -> None:
    """Truncated PDF with missing trailer or catalog must raise RejectedInputError."""
    corrupt_pdf = tmp_path / "truncated.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\n")  # Incomplete PDF

    with pytest.raises(RejectedInputError) as exc_info:
        check_pdf_pages(corrupt_pdf, max_pages=100)

    assert "corrupt or invalid pdf" in str(exc_info.value).lower()


@pytest.mark.gate5
def test_empty_zero_byte_file_rejected(tmp_path: Path) -> None:
    """Empty 0-byte file must raise RejectedInputError during type detection."""
    empty_file = tmp_path / "empty_doc.pdf"
    empty_file.write_bytes(b"")

    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(empty_file)

    assert "empty file" in str(exc_info.value).lower()


@pytest.mark.gate5
def test_corrupt_xlsx_archive_rejected(tmp_path: Path) -> None:
    """XLSX file with corrupt zip header or missing spreadsheet components must be rejected."""
    corrupt_xlsx = tmp_path / "corrupt.xlsx"
    corrupt_xlsx.write_bytes(b"PK\x03\x04corrupted_zip_archive_data")

    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(corrupt_xlsx)

    assert "corrupt or invalid xlsx" in str(exc_info.value).lower() or "not a valid zip" in str(exc_info.value).lower()


@pytest.mark.gate5
def test_macro_enabled_and_legacy_office_formats_rejected(tmp_path: Path) -> None:
    """Macro-enabled (.xlsm, .docm) and legacy binary (.xls) formats are explicitly rejected for security."""
    for ext in ["xlsm", "xls", "docm"]:
        bad_file = tmp_path / f"malicious.{ext}"
        bad_file.write_bytes(b"dummy macro content")

        with pytest.raises(RejectedInputError) as exc_info:
            detect_file_type(bad_file)

        assert "unsupported file format" in str(exc_info.value).lower()
        assert "macros" in str(exc_info.value).lower()


@pytest.mark.gate5
def test_non_utf8_binary_text_file_rejected(tmp_path: Path) -> None:
    """Text-based file containing non-UTF-8 binary bytes or null bytes must be rejected."""
    bad_txt = tmp_path / "invalid_encoding.txt"
    bad_txt.write_bytes(b"Valid prefix text \x00 null byte injected \xff\xfe binary")

    with pytest.raises(RejectedInputError) as exc_info:
        detect_file_type(bad_txt)

    assert "null bytes" in str(exc_info.value).lower() or "encoding error" in str(exc_info.value).lower()
