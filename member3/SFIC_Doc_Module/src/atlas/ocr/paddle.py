from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from atlas.ocr.tesseract import OcrLine, OcrPage, OcrWord
from atlas.ports.ocr import OcrEnginePort

logger = logging.getLogger(__name__)

try:
    import paddleocr  # type: ignore[import-not-found]

    _PADDLE_AVAILABLE = True
except ImportError:
    paddleocr = None
    _PADDLE_AVAILABLE = False


class PaddleEngine(OcrEnginePort):
    """PaddleOCR engine adapter implementing OcrEnginePort."""

    def __init__(self, lang: str = "en") -> None:
        if not _PADDLE_AVAILABLE:
            raise ImportError(
                "PaddleOCR is not available. Please install paddleocr and paddlepaddle "
                "(e.g. 'pip install paddleocr paddlepaddle' or 'uv pip install .[paddle]')."
            )
        self._lang = lang
        self._ocr = paddleocr.PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)

    @property
    def engine_name(self) -> str:
        """Name of the OCR engine."""
        return "paddle"

    @property
    def engine_version(self) -> str:
        """Version of the PaddleOCR package."""
        if paddleocr is not None:
            return getattr(paddleocr, "__version__", "unknown")
        return "unknown"

    def recognize(self, image: Any, langs: list[str] | None = None) -> OcrPage:
        """Recognize text in an image using PaddleOCR.

        Args:
            image: PIL.Image, numpy ndarray, or file path.
            langs: List of language codes (PaddleOCR uses its configured language by default).

        Returns:
            OcrPage dictionary.
        """
        if not _PADDLE_AVAILABLE:
            raise ImportError("PaddleOCR is not available.")

        if isinstance(image, (str, Path)):
            pil_img = Image.open(image)
            arr = np.array(pil_img.convert("RGB"))
        elif isinstance(image, Image.Image):
            arr = np.array(image.convert("RGB"))
        elif isinstance(image, np.ndarray):
            arr = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")

        result = self._ocr.ocr(arr, cls=True)

        lines: list[OcrLine] = []
        warnings: list[str] = []

        if result and isinstance(result, list):
            page_entries = result[0] if len(result) > 0 and isinstance(result[0], list) else result
            for entry in page_entries:
                if not entry or len(entry) < 2:
                    continue
                box, text_score = entry[0], entry[1]
                if not text_score:
                    continue
                line_text = str(text_score[0])
                score = float(text_score[1]) if len(text_score) > 1 and text_score[1] is not None else None

                xs = [int(pt[0]) for pt in box]
                ys = [int(pt[1]) for pt in box]
                bbox = [min(xs), min(ys), max(xs), max(ys)]

                # PaddleOCR supplies line-level score. Do not fabricate word scores.
                words_list = line_text.split()
                words: list[OcrWord] = [{"text": w, "conf": None, "bbox": bbox} for w in words_list]

                lines.append(
                    {
                        "text": line_text,
                        "words": words,
                        "bbox": bbox,
                        "conf_mean": score,
                    }
                )

        if not lines:
            warnings.append("No text detected by PaddleOCR engine.")

        raw_text = "\n".join(line["text"] for line in lines)
        active_langs = list(langs) if langs else [self._lang]

        return {
            "lines": lines,
            "raw_text": raw_text,
            "engine": self.engine_name,
            "version": self.engine_version,
            "langs": active_langs,
            "warnings": warnings,
        }


__all__ = ["PaddleEngine"]
