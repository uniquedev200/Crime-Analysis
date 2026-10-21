"""Ingest package for ATLAS Dev 3.

Provides intake detection, integrity verification, limits enforcement,
content-addressed original storage, and synthetic data validation.
"""

from __future__ import annotations

from atlas.ingest.detect import (
    REJECTED_MACRO_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    detect_file_type,
)
from atlas.ingest.integrity import (
    compute_sha256,
    verify_hash,
    write_receipt,
)
from atlas.ingest.limits import (
    check_file_size,
    check_image_pixels,
    check_pdf_pages,
)
from atlas.ingest.originals import (
    store_original,
)
from atlas.ingest.synthetic_guard import (
    check_synthetic,
    register_synthetic_files,
)

__all__ = [
    "REJECTED_MACRO_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "check_file_size",
    "check_image_pixels",
    "check_pdf_pages",
    "check_synthetic",
    "compute_sha256",
    "detect_file_type",
    "register_synthetic_files",
    "store_original",
    "verify_hash",
    "write_receipt",
]
