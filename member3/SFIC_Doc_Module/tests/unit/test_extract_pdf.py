"""Unit tests for PDF extraction, digital vs OCR routing, tabular PDF detection, and error resilience.

All tests are marked @pytest.mark.gate1 and use UTF-8 encoding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import reportlab.pdfgen.canvas as canvas
from PIL import Image

from atlas.contracts.enums import PageMethod
from atlas.errors import RejectedInputError
from atlas.extract.pdf import PdfBackend, PdfExtractor, needs_ocr
from atlas.extract.tabular_pdf_detect import is_tabular_pdf


class FakeOcrResult:
    """Mock result from OCR engine."""

    def __init__(self, raw_text: str) -> None:
        self.raw_text = raw_text
        self.lines = [type("Line", (), {"text": line})() for line in raw_text.splitlines() if line]


class FakeOcrEngine:
    """Mock OCR engine adhering to OcrEnginePort for testing without pytesseract binary."""

    def __init__(self, output_text: str = "Extracted OCR text line 1\nExtracted OCR line 2") -> None:
        self._output_text = output_text
        self.call_count = 0

    @property
    def engine_name(self) -> str:
        return "fake_ocr_engine"

    @property
    def engine_version(self) -> str:
        return "1.0.0-mock"

    def recognize(self, image: Any, langs: list[str]) -> Any:
        self.call_count += 1
        return FakeOcrResult(self._output_text)


def _create_digital_pdf(path: Path, text: str) -> Path:
    c = canvas.Canvas(str(path), invariant=1)
    c.drawString(100, 700, text)
    c.save()
    return path


def _create_scanned_pdf(path: Path) -> Path:
    """Create a PDF with no text layer (only geometric drawing), simulating a scanned image."""
    c = canvas.Canvas(str(path), invariant=1)
    c.rect(100, 100, 300, 300, fill=1)
    c.save()
    return path


def _create_mixed_pdf(path: Path, p1_text: str) -> Path:
    """Create a 2-page PDF: page 1 digital text, page 2 scanned/blank."""
    c = canvas.Canvas(str(path), invariant=1)
    # Page 1: digital
    c.drawString(100, 700, p1_text)
    c.showPage()
    # Page 2: scanned / geometric only
    c.rect(50, 50, 200, 200, fill=1)
    c.showPage()
    c.save()
    return path


@pytest.mark.gate1
def test_needs_ocr_evaluation() -> None:
    """Verify needs_ocr criteria for short text, garbled text, and normal text."""
    # Too short (< 25 non-whitespace chars)
    assert needs_ocr("Page 1", min_chars=25) is True
    assert needs_ocr("", min_chars=25) is True

    # Garbled/noise (printable/letter ratio < 0.6)
    noise = "!@#$%^&*()_+=-~`[]{}|:;'<>,.?/" * 2
    assert needs_ocr(noise, min_chars=25, min_ratio=0.6) is True

    # Normal narrative text (high letter ratio and enough characters)
    normal = "This is a detailed narrative report containing plenty of characters for testing."
    assert needs_ocr(normal, min_chars=25, min_ratio=0.6) is False

    # Alphanumeric tabular line
    tabular = "2026-10-15  10:00:00  9876543210  9876543211  500.00"
    assert needs_ocr(tabular, min_chars=25, min_ratio=0.6) is False


@pytest.mark.gate1
def test_digital_pdf_routing(tmp_path: Path) -> None:
    """Pure digital PDF is extracted with PageMethod.PDF_TEXT and OCR engine is not invoked."""
    pdf_path = tmp_path / "digital.pdf"
    content = "The FIR registration indicates complainant reported incident at 10:00 hours."
    _create_digital_pdf(pdf_path, content)

    fake_ocr = FakeOcrEngine()
    extractor = PdfExtractor(ocr_engine=fake_ocr)

    pages_info, units = extractor.extract_document(pdf_path, doc_id="DOC-DIGITAL")

    assert len(pages_info) == 1
    assert pages_info[0].method == PageMethod.PDF_TEXT
    assert pages_info[0].page == 1
    assert fake_ocr.call_count == 0

    assert len(units) >= 1
    page_unit = next(u for u in units if u.unit_id == "DOC-DIGITAL:p001")
    assert content in page_unit.text


@pytest.mark.gate1
def test_scanned_pdf_routing(tmp_path: Path) -> None:
    """Scanned/empty text layer PDF triggers OCR fallback with PageMethod.OCR."""
    pdf_path = tmp_path / "scanned.pdf"
    _create_scanned_pdf(pdf_path)

    fake_ocr = FakeOcrEngine(output_text="Simulated OCR result from scanned page")
    extractor = PdfExtractor(ocr_engine=fake_ocr)

    pages_info, units = extractor.extract_document(pdf_path, doc_id="DOC-SCANNED")

    assert len(pages_info) == 1
    assert pages_info[0].method == PageMethod.OCR
    assert fake_ocr.call_count == 1

    page_unit = next(u for u in units if u.unit_id == "DOC-SCANNED:p001")
    assert "Simulated OCR result" in page_unit.text


@pytest.mark.gate1
def test_mixed_pdf_routing(tmp_path: Path) -> None:
    """Multi-page PDF with digital and scanned pages routes each page appropriately."""
    pdf_path = tmp_path / "mixed.pdf"
    p1_text = "This is a digital page with sufficient length for testing extraction."
    _create_mixed_pdf(pdf_path, p1_text)

    fake_ocr = FakeOcrEngine(output_text="Page 2 OCR recognized output")
    extractor = PdfExtractor(ocr_engine=fake_ocr)

    pages_info, units = extractor.extract_document(pdf_path, doc_id="DOC-MIXED")

    assert len(pages_info) == 2
    # Page 1: digital
    assert pages_info[0].page == 1
    assert pages_info[0].method == PageMethod.PDF_TEXT

    # Page 2: scanned -> OCR
    assert pages_info[1].page == 2
    assert pages_info[1].method == PageMethod.OCR

    # OCR called exactly once (for page 2)
    assert fake_ocr.call_count == 1

    p1_unit = next(u for u in units if u.unit_id == "DOC-MIXED:p001")
    p2_unit = next(u for u in units if u.unit_id == "DOC-MIXED:p002")
    assert p1_text in p1_unit.text
    assert "Page 2 OCR recognized output" in p2_unit.text


@pytest.mark.gate1
def test_render_page_to_pil(tmp_path: Path) -> None:
    """render_page produces valid PIL Image at specified DPI."""
    pdf_path = tmp_path / "render.pdf"
    _create_digital_pdf(pdf_path, "Render test content")

    extractor = PdfExtractor()
    img = extractor.render_page(pdf_path, page=0, dpi=150)

    assert isinstance(img, Image.Image)
    assert img.size[0] > 0
    assert img.size[1] > 0


@pytest.mark.gate1
def test_encrypted_pdf_rejection(tmp_path: Path) -> None:
    """Encrypted PDF raises RejectedInputError with explicit explanation."""
    enc_path = tmp_path / "locked.pdf"
    c = canvas.Canvas(str(enc_path), encrypt="password123", invariant=1)
    c.drawString(100, 700, "Secret content")
    c.save()

    extractor = PdfExtractor()
    assert extractor.is_encrypted(enc_path) is True

    with pytest.raises(RejectedInputError) as exc_info:
        extractor.extract_document(enc_path, doc_id="DOC-LOCKED")
    assert "encrypted" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_corrupt_pdf_rejection(tmp_path: Path) -> None:
    """Corrupt PDF raises RejectedInputError."""
    bad_pdf = tmp_path / "broken.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4\ncorrupted stream end")

    extractor = PdfExtractor()
    with pytest.raises(RejectedInputError) as exc_info:
        extractor.extract_document(bad_pdf, doc_id="DOC-BROKEN")
    assert "corrupt" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


@pytest.mark.gate1
def test_failed_page_recorded_never_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A page whose extraction raises an exception is recorded with warnings and never dropped."""
    pdf_path = tmp_path / "resilient.pdf"
    _create_digital_pdf(pdf_path, "Standard digital text on page 1")

    extractor = PdfExtractor()

    # Monkeypatch extract_page_text to simulate error on page extraction
    def failing_extract(path: Path, page: int) -> str:
        raise RuntimeError("Simulated transient page extraction crash")

    monkeypatch.setattr(extractor, "extract_page_text", failing_extract)

    pages_info, units = extractor.extract_document(pdf_path, doc_id="DOC-FAILPAGE")

    # Page must still be recorded in pages_info
    assert len(pages_info) == 1
    assert pages_info[0].page == 1
    assert len(pages_info[0].warnings) > 0
    assert "extraction failed" in pages_info[0].warnings[0].lower()

    # Unit must still exist
    page_unit = next(u for u in units if u.unit_id == "DOC-FAILPAGE:p001")
    assert page_unit is not None
    assert len(page_unit.warnings) > 0


@pytest.mark.gate1
def test_tabular_pdf_detector() -> None:
    """is_tabular_pdf identifies table layouts with >= 3 numeric columns on >= 30% lines."""
    narrative_text = (
        "First Information Report registered at Cyber Crime Police Station.\n"
        "Complainant reported loss of funds via unauthorized online transfer.\n"
        "Investigating officer interviewed witness regarding incident timing.\n"
        "Suspect was reportedly seen in commercial area during afternoon hours.\n"
        "Case case_id CASE_001 assigned to senior inspector Sharma.\n"
    )
    assert is_tabular_pdf(narrative_text) is False

    tabular_cdr_text = (
        "Date | Time | Caller | Callee | Duration | Cell_ID\n"
        "2026-01-01 10:15 9876543210 9876543211 120 40401\n"
        "2026-01-01 10:45 9876543210 9876543212 45 40402\n"
        "2026-01-01 11:20 9876543210 9876543213 360 40401\n"
        "2026-01-01 12:05 9876543211 9876543210 80 40403\n"
    )
    assert is_tabular_pdf(tabular_cdr_text) is True


@pytest.mark.gate1
def test_pdf_backend_protocol_alias() -> None:
    """PdfBackend alias exists and fulfills PdfBackendPort protocol."""
    backend = PdfBackend()
    assert hasattr(backend, "extract_text")
    assert hasattr(backend, "page_count")
    assert hasattr(backend, "render_page")
    assert hasattr(backend, "is_encrypted")


@pytest.mark.gate1
def test_pdf_methods_and_bounds(tmp_path: Path) -> None:
    """PdfExtractor page_count, extract_text alias, and bounds checking."""
    pdf_path = tmp_path / "bounds.pdf"
    _create_digital_pdf(pdf_path, "Content on page for boundary test")

    extractor = PdfExtractor()
    assert extractor.page_count(pdf_path) == 1
    # extract_text alias
    assert "boundary" in extractor.extract_text(pdf_path, 0)
    # 1-indexed page
    assert "boundary" in extractor.extract_page_text(pdf_path, 1)

    # Out of bounds raises IndexError
    with pytest.raises(IndexError):
        extractor.extract_page_text(pdf_path, 5)

    with pytest.raises(IndexError):
        extractor.render_page(pdf_path, 5)


@pytest.mark.gate1
def test_scanned_pdf_without_ocr_engine_records_warning(tmp_path: Path) -> None:
    """When a scanned page requires OCR but no OCR engine is provided, a warning is recorded."""
    pdf_path = tmp_path / "no_engine.pdf"
    _create_scanned_pdf(pdf_path)

    extractor = PdfExtractor(ocr_engine=None)
    pages_info, units = extractor.extract_document(pdf_path, doc_id="DOC-NOENG")

    assert len(pages_info) == 1
    assert len(units) >= 1
    assert any("requires ocr" in w.lower() for w in pages_info[0].warnings)
