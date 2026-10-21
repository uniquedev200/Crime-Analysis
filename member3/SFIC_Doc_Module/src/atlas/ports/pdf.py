from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PdfBackendPort(Protocol):
    """Port interface for PDF extraction and rendering backends."""

    def extract_text(self, path: Path, page: int) -> str:
        """Extract text layer from a specific page."""
        ...

    def page_count(self, path: Path) -> int:
        """Return total number of pages in the PDF document."""
        ...

    def render_page(self, path: Path, page: int, dpi: int) -> Any:
        """Render a PDF page to an image (e.g. PIL Image) at specified DPI."""
        ...

    def is_encrypted(self, path: Path) -> bool:
        """Return True if PDF document is encrypted or password-protected."""
        ...


__all__ = ["PdfBackendPort"]
