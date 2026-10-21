from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OcrEnginePort(Protocol):
    """Port interface for OCR engine adapters."""

    @property
    def engine_name(self) -> str:
        """Name of the OCR engine (e.g. 'tesseract', 'paddle')."""
        ...

    @property
    def engine_version(self) -> str:
        """Version of the OCR engine."""
        ...

    def recognize(self, image: Any, langs: list[str]) -> Any:
        """Recognize text in an image returning an OcrPage-like structure or dict."""
        ...


__all__ = ["OcrEnginePort"]
