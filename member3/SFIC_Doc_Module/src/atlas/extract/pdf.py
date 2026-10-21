"""PDF text extraction and page routing for ATLAS Dev 3.

Uses pypdfium2 for digital text extraction and page rendering.
Routes pages between digital text and OCR based on character counts and letter ratios.
Does NOT import pytesseract directly (relies on injected OcrEngine port).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pypdfium2 as pdfium
from PIL import Image

from atlas.contracts.enums import PageMethod
from atlas.contracts.ids import make_unit_id_line, make_unit_id_page
from atlas.contracts.records import PageInfo
from atlas.errors import RejectedInputError
from atlas.extract.units import Unit


def needs_ocr(text: str, min_chars: int = 25, min_ratio: float = 0.6) -> bool:
    """Determine whether a page's extracted text layer requires OCR fallback.

    Triggers OCR if:
    1. Count of non-whitespace characters is less than min_chars.
    2. Ratio of printable letters (or alphanumeric characters) to non-whitespace characters is < min_ratio.
    """
    non_ws = "".join(text.split())
    if len(non_ws) < min_chars:
        return True

    # Check printable letters ratio
    letters = sum(1 for c in non_ws if c.isalpha() and c.isprintable())
    if letters / len(non_ws) >= min_ratio:
        return False

    # Check alphanumeric ratio for numbers/tables/structured data
    alnum = sum(1 for c in non_ws if c.isalnum() and c.isprintable())
    return (alnum / len(non_ws)) < min_ratio


class PdfExtractor:
    """PDF extraction engine implementing text-layer extraction, OCR routing, and page rendering."""

    def __init__(
        self,
        ocr_engine: Any = None,
        min_chars: int = 25,
        min_ratio: float = 0.6,
        dpi: int = 300,
        ocr_langs: list[str] | None = None,
    ) -> None:
        self.ocr_engine = ocr_engine
        self.min_chars = min_chars
        self.min_ratio = min_ratio
        self.dpi = dpi
        self.ocr_langs = ocr_langs or ["eng"]

    def is_encrypted(self, path: Path) -> bool:
        """Check if PDF is password-protected or encrypted."""
        if not isinstance(path, Path):
            path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            doc = pdfium.PdfDocument(str(path))
            doc.close()
            return False
        except Exception as exc:
            msg = str(exc).lower()
            if "password" in msg:
                return True
            try:
                with path.open("rb") as f:
                    content = f.read(8192)
                if b"/Encrypt" in content:
                    return True
            except Exception:
                pass
            return False

    def page_count(self, path: Path) -> int:
        """Return total page count of PDF document."""
        if not isinstance(path, Path):
            path = Path(path)

        if self.is_encrypted(path):
            raise RejectedInputError(f"Encrypted or password-protected PDF is not supported: '{path.name}'")

        try:
            doc = pdfium.PdfDocument(str(path))
        except Exception as exc:
            raise RejectedInputError(f"Corrupt or invalid PDF file '{path.name}': {exc}") from exc

        try:
            return len(doc)
        finally:
            doc.close()

    def extract_page_text(self, path: Path, page: int) -> str:
        """Extract digital text layer from a specific page (0-indexed or 1-indexed)."""
        if not isinstance(path, Path):
            path = Path(path)

        if self.is_encrypted(path):
            raise RejectedInputError(f"Encrypted or password-protected PDF is not supported: '{path.name}'")

        try:
            doc = pdfium.PdfDocument(str(path))
        except Exception as exc:
            raise RejectedInputError(f"Corrupt or invalid PDF file '{path.name}': {exc}") from exc

        try:
            total = len(doc)
            idx = page if 0 <= page < total else (page - 1 if 1 <= page <= total else page)
            if not (0 <= idx < total):
                raise IndexError(f"Page index {page} out of range (document has {total} pages)")
            page_obj = doc[idx]
            textpage = page_obj.get_textpage()
            return str(textpage.get_text_range())
        finally:
            doc.close()

    def extract_text(self, path: Path, page: int) -> str:
        """Alias conforming to PdfBackendPort protocol."""
        return self.extract_page_text(path, page)

    def render_page(self, path: Path, page: int, dpi: int | None = None) -> Image.Image:
        """Render a specific PDF page to PIL Image at requested DPI."""
        if not isinstance(path, Path):
            path = Path(path)

        if self.is_encrypted(path):
            raise RejectedInputError(f"Encrypted or password-protected PDF is not supported: '{path.name}'")

        target_dpi = dpi or self.dpi
        try:
            doc = pdfium.PdfDocument(str(path))
        except Exception as exc:
            raise RejectedInputError(f"Corrupt or invalid PDF file '{path.name}': {exc}") from exc

        try:
            total = len(doc)
            idx = page if 0 <= page < total else (page - 1 if 1 <= page <= total else page)
            if not (0 <= idx < total):
                raise IndexError(f"Page index {page} out of range (document has {total} pages)")
            page_obj = doc[idx]
            scale = target_dpi / 72.0
            bitmap = page_obj.render(scale=scale)
            return cast(Image.Image, bitmap.to_pil())
        finally:
            doc.close()

    def extract_document(
        self,
        path: Path,
        doc_id: str,
    ) -> tuple[list[PageInfo], list[Unit]]:
        """Extract entire document with page-by-page digital text vs. OCR routing.

        Returns (list[PageInfo], list[Unit]).
        Never drops a page; failed pages are recorded with warnings.
        """
        if not isinstance(path, Path):
            path = Path(path)

        if self.is_encrypted(path):
            raise RejectedInputError(f"Encrypted or password-protected PDF is not supported: '{path.name}'")

        total_pages = self.page_count(path)
        pages_info: list[PageInfo] = []
        units: list[Unit] = []

        for page_idx in range(total_pages):
            page_num = page_idx + 1  # 1-indexed for units & PageInfo
            page_warnings: list[str] = []
            page_text = ""
            method = PageMethod.PDF_TEXT

            try:
                raw_text = self.extract_page_text(path, page_idx)
                if needs_ocr(raw_text, min_chars=self.min_chars, min_ratio=self.min_ratio):
                    if self.ocr_engine is not None:
                        method = PageMethod.OCR
                        img = self.render_page(path, page_idx, dpi=self.dpi)
                        ocr_res = self.ocr_engine.recognize(img, self.ocr_langs)
                        if hasattr(ocr_res, "raw_text"):
                            page_text = str(ocr_res.raw_text)
                        elif isinstance(ocr_res, dict):
                            page_text = str(ocr_res.get("raw_text", ocr_res.get("text", "")))
                        elif isinstance(ocr_res, str):
                            page_text = ocr_res
                        else:
                            page_text = str(ocr_res)
                    else:
                        page_warnings.append(f"Page {page_num} requires OCR but no OCR engine was provided")
                        page_text = raw_text
                else:
                    page_text = raw_text
                    method = PageMethod.PDF_TEXT
            except Exception as exc:
                page_warnings.append(f"Page {page_num} extraction failed: {exc}")
                page_text = ""
                method = PageMethod.PDF_TEXT

            pages_info.append(
                PageInfo(
                    page=page_num,
                    method=method,
                    chars=len(page_text),
                    warnings=page_warnings,
                )
            )

            lines = page_text.splitlines()

            # Create page unit
            page_unit_id = make_unit_id_page(doc_id, page_num)
            units.append(
                Unit(
                    unit_id=page_unit_id,
                    text=page_text,
                    page=page_num,
                    line_start=1 if lines else None,
                    line_end=len(lines) if lines else None,
                    method=method.value,
                    doc_id=doc_id,
                    warnings=page_warnings,
                )
            )

            # Create line units
            for line_idx, line in enumerate(lines, start=1):
                line_unit_id = make_unit_id_line(doc_id, page_num, line_idx)
                units.append(
                    Unit(
                        unit_id=line_unit_id,
                        text=line,
                        page=page_num,
                        line_start=line_idx,
                        line_end=line_idx,
                        method=method.value,
                        doc_id=doc_id,
                    )
                )

        return pages_info, units


# Alias for compatibility with ports/pdf.py and PLAN.md
PdfBackend = PdfExtractor

__all__ = ["PdfBackend", "PdfExtractor", "needs_ocr"]
