"""Size, page, and pixel limits enforcement for ATLAS Dev 3 ingestion.

All limit checks raise RejectedInputError with explicit, actionable reasons.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from atlas.errors import RejectedInputError


def check_file_size(path: Path, max_mb: int) -> None:
    """Enforce maximum file size limit in megabytes.

    Raises RejectedInputError if the file size exceeds max_mb.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    size_bytes = path.stat().st_size
    max_bytes = max_mb * 1024 * 1024
    if size_bytes > max_bytes:
        mb_actual = size_bytes / (1024 * 1024)
        raise RejectedInputError(
            f"File size {size_bytes} bytes ({mb_actual:.2f} MB) exceeds maximum allowed limit of {max_mb} MB ({max_bytes} bytes)"
        )


def check_pdf_pages(path: Path, max_pages: int) -> None:
    """Enforce maximum page count limit on PDF documents using pypdfium2.

    Raises RejectedInputError if page count exceeds max_pages, or if the PDF
    is password-protected/encrypted or corrupt.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as exc:
        msg = str(exc).lower()
        if "password" in msg:
            raise RejectedInputError(f"Encrypted or password-protected PDF is not supported: {exc}") from exc
        raise RejectedInputError(f"Corrupt or invalid PDF file '{path.name}': {exc}") from exc

    try:
        page_count = len(doc)
        if page_count > max_pages:
            raise RejectedInputError(f"PDF page count {page_count} exceeds maximum allowed limit of {max_pages} pages")
    finally:
        doc.close()


def check_image_pixels(path: Path, max_pixels: int) -> None:
    """Enforce maximum pixel count on image files to prevent decompression bombs.

    Configures PIL Image.MAX_IMAGE_PIXELS and treats DecompressionBombError as
    RejectedInputError.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    # Set PIL safety threshold
    Image.MAX_IMAGE_PIXELS = max_pixels

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                width, height = img.size
                total_pixels = width * height
                if total_pixels > max_pixels:
                    raise RejectedInputError(
                        f"Image pixel count {total_pixels} ({width}x{height}) exceeds maximum limit of {max_pixels} pixels"
                    )
    except Image.DecompressionBombError as exc:
        raise RejectedInputError(f"Image rejected as potential decompression bomb: {exc}") from exc
    except RejectedInputError:
        raise
    except Exception as exc:
        raise RejectedInputError(f"Failed to inspect image '{path.name}' dimensions: {exc}") from exc


__all__ = ["check_file_size", "check_image_pixels", "check_pdf_pages"]
