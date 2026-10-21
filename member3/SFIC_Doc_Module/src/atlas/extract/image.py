"""Image input extraction for ATLAS Dev 3.

Loads image using Pillow, verifies dimensions, and invokes injected OCR engine.
Does NOT import pytesseract directly (relies on injected OcrEngine port).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from atlas.errors import RejectedInputError


def extract_from_image(
    path: Path,
    ocr_engine: Any,
    langs: list[str] | None = None,
) -> dict[str, Any]:
    """Load image and invoke injected OCR engine.

    Returns dict containing raw_text, lines, engine metadata, and page structure.
    Raises RejectedInputError if the image is corrupt or exceeds size limits.
    """
    if not isinstance(path, Path):
        path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    if ocr_engine is None:
        raise ValueError("ocr_engine must be provided for image extraction")

    try:
        with Image.open(path) as img:
            # Load pixel data into memory so file handle can close safely
            img_copy = img.copy()
    except Image.DecompressionBombError as exc:
        raise RejectedInputError(f"Image rejected as potential decompression bomb: {exc}") from exc
    except Exception as exc:
        raise RejectedInputError(f"Corrupt or invalid image file '{path.name}': {exc}") from exc

    target_langs = langs or ["eng"]
    ocr_result = ocr_engine.recognize(img_copy, target_langs)

    # Normalize extracted text and lines across diverse OCR engine implementations
    if hasattr(ocr_result, "raw_text"):
        raw_text = str(ocr_result.raw_text)
    elif isinstance(ocr_result, dict):
        raw_text = str(ocr_result.get("raw_text", ocr_result.get("text", "")))
    elif isinstance(ocr_result, str):
        raw_text = ocr_result
    else:
        raw_text = str(ocr_result)

    lines: list[str] = []
    if hasattr(ocr_result, "lines"):
        for l_obj in ocr_result.lines:
            line_str = getattr(l_obj, "text", str(l_obj))
            lines.append(str(line_str))
    elif isinstance(ocr_result, dict) and "lines" in ocr_result:
        for l_item in ocr_result["lines"]:
            if isinstance(l_item, dict):
                lines.append(str(l_item.get("text", "")))
            else:
                lines.append(str(l_item))
    else:
        lines = raw_text.splitlines()

    engine_name = getattr(ocr_engine, "engine_name", "injected_ocr")

    return {
        "path": str(path),
        "raw_text": raw_text,
        "text": raw_text,
        "lines": lines,
        "engine": engine_name,
        "ocr_page": ocr_result,
        "method": "image_ocr",
    }


__all__ = ["extract_from_image"]
