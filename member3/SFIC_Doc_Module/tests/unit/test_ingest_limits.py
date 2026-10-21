"""Unit tests for ingestion limits (file size, PDF pages, image pixels, decompression bomb).

All tests are marked @pytest.mark.gate1 and use UTF-8 encoding.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import reportlab.pdfgen.canvas as canvas
from PIL import Image

from atlas.errors import RejectedInputError
from atlas.ingest.limits import (
    check_file_size,
    check_image_pixels,
    check_pdf_pages,
)


def _generate_multipage_pdf(path: Path, num_pages: int) -> Path:
    """Generate deterministic multi-page PDF using reportlab invariant=1."""
    c = canvas.Canvas(str(path), invariant=1)
    for i in range(num_pages):
        c.drawString(100, 700, f"Synthetic Page {i + 1} Content")
        c.showPage()
    c.save()
    return path


@pytest.mark.gate1
def test_check_file_size_within_and_exceeding(tmp_path: Path) -> None:
    """File size check passes within limit and raises RejectedInputError when exceeding."""
    file_path = tmp_path / "sample.bin"
    # Create 2 KB file
    file_path.write_bytes(b"x" * 2048)

    # 1 MB limit -> passes
    check_file_size(file_path, max_mb=1)

    # Fake larger file (e.g. 1500 bytes with limit 0 MB if 0 allowed, or 100 bytes limit)
    # Let's test with a 2 MB file and 1 MB limit
    big_file = tmp_path / "big.bin"
    big_file.write_bytes(b"x" * (2 * 1024 * 1024 + 10))
    with pytest.raises(RejectedInputError) as exc_info:
        check_file_size(big_file, max_mb=1)

    err = str(exc_info.value)
    assert "exceeds maximum allowed limit of 1 MB" in err


@pytest.mark.gate1
def test_check_pdf_pages_limit(tmp_path: Path) -> None:
    """PDF page check passes for allowed page counts and raises when exceeding."""
    pdf_3pages = _generate_multipage_pdf(tmp_path / "doc_3p.pdf", 3)

    # 5 max pages -> passes
    check_pdf_pages(pdf_3pages, max_pages=5)

    # 2 max pages -> raises RejectedInputError
    with pytest.raises(RejectedInputError) as exc_info:
        check_pdf_pages(pdf_3pages, max_pages=2)
    assert "exceeds maximum allowed limit of 2 pages" in str(exc_info.value)


@pytest.mark.gate1
def test_check_pdf_pages_encrypted_rejection(tmp_path: Path) -> None:
    """Encrypted/password-protected PDF is rejected with RejectedInputError."""
    enc_pdf = tmp_path / "encrypted.pdf"
    c = canvas.Canvas(str(enc_pdf), encrypt="super_secret_key", invariant=1)
    c.drawString(100, 700, "Secret Protected Data")
    c.save()

    with pytest.raises(RejectedInputError) as exc_info:
        check_pdf_pages(enc_pdf, max_pages=10)
    assert "encrypted" in str(exc_info.value).lower() or "password" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_check_pdf_pages_corrupt_rejection(tmp_path: Path) -> None:
    """Corrupt PDF file is rejected with RejectedInputError."""
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\ncorrupted header invalid stream end")

    with pytest.raises(RejectedInputError) as exc_info:
        check_pdf_pages(corrupt_pdf, max_pages=10)
    assert "corrupt" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_check_image_pixels_within_and_exceeding(tmp_path: Path) -> None:
    """check_image_pixels enforces pixel threshold and rejects oversized dimensions."""
    img_path = tmp_path / "small.png"
    img = Image.new("RGB", (200, 200), color="white")
    img.save(str(img_path))

    # 200 * 200 = 40,000 pixels. Threshold 50,000 -> passes
    check_image_pixels(img_path, max_pixels=50_000)

    # Threshold 30,000 -> raises RejectedInputError
    with pytest.raises(RejectedInputError) as exc_info:
        check_image_pixels(img_path, max_pixels=30_000)
    err = str(exc_info.value)
    assert "40000" in err
    assert "exceeds maximum limit" in err


@pytest.mark.gate1
def test_check_image_decompression_bomb_rejection(tmp_path: Path) -> None:
    """Potential decompression bomb images trigger RejectedInputError."""
    bomb_path = tmp_path / "huge.png"
    # Create image with dimensions exceeding threshold
    img = Image.new("RGB", (2000, 2000), color="black")
    img.save(str(bomb_path))

    # Limit to 100,000 pixels so Image.MAX_IMAGE_PIXELS triggers
    with pytest.raises(RejectedInputError) as exc_info:
        check_image_pixels(bomb_path, max_pixels=100_000)
    assert "exceeds maximum limit" in str(exc_info.value).lower() or "decompression bomb" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_limits_file_not_found(tmp_path: Path) -> None:
    """Non-existent files raise FileNotFoundError across all limits functions."""
    missing = tmp_path / "not_there.bin"
    with pytest.raises(FileNotFoundError):
        check_file_size(missing, max_mb=10)
    with pytest.raises(FileNotFoundError):
        check_pdf_pages(missing, max_pages=10)
    with pytest.raises(FileNotFoundError):
        check_image_pixels(missing, max_pixels=100_000)
