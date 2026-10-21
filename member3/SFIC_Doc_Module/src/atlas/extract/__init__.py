"""Extract package for ATLAS Dev 3.

Provides text, image, JSON, and PDF extraction, OCR routing, unit creation,
and tabular PDF detection.
"""

from __future__ import annotations

from atlas.extract.image import extract_from_image
from atlas.extract.jsonfile import extract_json_file, extract_json_file_units
from atlas.extract.pdf import PdfBackend, PdfExtractor, needs_ocr
from atlas.extract.tabular_pdf_detect import is_tabular_pdf
from atlas.extract.text import extract_text_file, extract_text_file_units
from atlas.extract.units import (
    Unit,
    create_json_pointer_unit,
    create_line_units,
    create_page_units,
    create_text_line_units,
)

__all__ = [
    "PdfBackend",
    "PdfExtractor",
    "Unit",
    "create_json_pointer_unit",
    "create_line_units",
    "create_page_units",
    "create_text_line_units",
    "extract_from_image",
    "extract_json_file",
    "extract_json_file_units",
    "extract_text_file",
    "extract_text_file_units",
    "is_tabular_pdf",
    "needs_ocr",
]
