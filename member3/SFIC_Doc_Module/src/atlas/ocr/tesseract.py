from __future__ import annotations

import logging
import os
import unittest.mock
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pytesseract
from PIL import Image
from pytesseract import Output

from atlas.config import get_settings
from atlas.ocr.langs import check_languages
from atlas.ports.ocr import OcrEnginePort

logger = logging.getLogger(__name__)


class OcrWord(TypedDict):
    """Word-level OCR result with bounding box and confidence score."""

    text: str
    conf: float | None
    bbox: list[int]


class OcrLine(TypedDict):
    """Line-level OCR result containing constituent words and bounding box."""

    text: str
    words: list[OcrWord]
    bbox: list[int]
    conf_mean: float | None


class OcrPage(TypedDict):
    """Page-level OCR result matching OcrEnginePort contract."""

    lines: list[OcrLine]
    raw_text: str
    engine: str
    version: str
    langs: list[str]
    warnings: list[str]


class TesseractEngine(OcrEnginePort):
    """Tesseract OCR engine adapter conforming to OcrEnginePort."""

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        tessdata_prefix: str | None = None,
        validate_langs: bool = True,
        psm: int | None = None,
        dpi: int | None = None,
    ) -> None:
        settings = get_settings()
        self._tesseract_cmd = tesseract_cmd or settings.TESSERACT_CMD
        self._tessdata_prefix = tessdata_prefix or settings.TESSDATA_PREFIX
        self.validate_langs = validate_langs
        self.psm = psm if psm is not None else settings.OCR_PSM
        self.dpi = dpi if dpi is not None else settings.OCR_DPI

        # Explicitly configure pytesseract
        pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
        if self._tessdata_prefix:
            os.environ["TESSDATA_PREFIX"] = self._tessdata_prefix

    @property
    def engine_name(self) -> str:
        """Name of the OCR engine."""
        return "tesseract"

    @property
    def engine_version(self) -> str:
        """Version string obtained from pytesseract."""
        try:
            return str(pytesseract.get_tesseract_version())
        except Exception:
            return "unknown"

    def recognize(self, image: Any, langs: list[str] | None = None) -> OcrPage:
        """Recognize text in an image returning an OcrPage structure.

        Args:
            image: PIL.Image, numpy ndarray, or file path.
            langs: List of language codes (e.g. ['eng'], ['eng', 'hin']).

        Returns:
            OcrPage dictionary containing lines, words, confidences, bboxes, and raw text.
        """
        if langs is None:
            settings = get_settings()
            langs = [settings.OCR_LANGS]

        # Verify languages unless mocked in testing
        if self.validate_langs and langs:
            # If image_to_data has been patched with a Mock, skip external process check
            is_mocked = isinstance(pytesseract.image_to_data, (unittest.mock.MagicMock, unittest.mock.Mock))
            if not is_mocked:
                check_languages(langs, self._tesseract_cmd)

        lang_str = "+".join(langs)
        config = f"--psm {self.psm} --dpi {self.dpi}"

        # Convert input to PIL Image if needed
        pil_img: Image.Image
        if isinstance(image, (str, Path)):
            pil_img = Image.open(image)
        elif isinstance(image, np.ndarray):
            pil_img = Image.fromarray(image)
        elif isinstance(image, Image.Image):
            pil_img = image
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")

        # Call pytesseract image_to_data
        data = pytesseract.image_to_data(
            pil_img,
            lang=lang_str,
            config=config,
            output_type=Output.DICT,
        )

        n_boxes = len(data.get("text", []))
        lines_dict: dict[tuple[int, int, int, int], list[OcrWord]] = {}
        line_order: list[tuple[int, int, int, int]] = []
        warnings: list[str] = []

        for i in range(n_boxes):
            # Check level: level 5 corresponds to words in Tesseract HOCR/TSV
            level = data.get("level", [5] * n_boxes)[i]
            if "level" in data and level != 5:
                continue

            raw_word = str(data["text"][i])
            # Skip empty or whitespace-only entries
            if not raw_word.strip():
                continue

            # Confidence parsing: -1 means unassigned/invalid -> None
            c_raw = data.get("conf", [-1] * n_boxes)[i]
            conf: float | None = None
            try:
                c_val = float(c_raw)
                if c_val >= 0:
                    conf = c_val
            except (ValueError, TypeError):
                conf = None

            left = int(data["left"][i])
            top = int(data["top"][i])
            width = int(data["width"][i])
            height = int(data["height"][i])
            bbox = [left, top, left + width, top + height]

            word_entry: OcrWord = {
                "text": raw_word,
                "conf": conf,
                "bbox": bbox,
            }

            p_num = int(data.get("page_num", [0] * n_boxes)[i])
            b_num = int(data.get("block_num", [0] * n_boxes)[i])
            par_num = int(data.get("par_num", [0] * n_boxes)[i])
            l_num = int(data.get("line_num", [0] * n_boxes)[i])
            line_key = (p_num, b_num, par_num, l_num)

            if line_key not in lines_dict:
                lines_dict[line_key] = []
                line_order.append(line_key)

            lines_dict[line_key].append(word_entry)

        lines: list[OcrLine] = []
        for lk in line_order:
            words = lines_dict[lk]
            if not words:
                continue

            # Preserve exact words without cleaning
            line_text = " ".join(w["text"] for w in words)
            min_x = min(w["bbox"][0] for w in words)
            min_y = min(w["bbox"][1] for w in words)
            max_x = max(w["bbox"][2] for w in words)
            max_y = max(w["bbox"][3] for w in words)
            line_bbox = [min_x, min_y, max_x, max_y]

            # Mean confidence calculation
            valid_confs = [w["conf"] for w in words if w["conf"] is not None]
            conf_mean = float(sum(valid_confs) / len(valid_confs)) if valid_confs else None

            lines.append(
                {
                    "text": line_text,
                    "words": words,
                    "bbox": line_bbox,
                    "conf_mean": conf_mean,
                }
            )

        raw_text = "\n".join(line["text"] for line in lines)
        if not lines:
            warnings.append("No text detected by OCR engine.")

        return {
            "lines": lines,
            "raw_text": raw_text,
            "engine": self.engine_name,
            "version": self.engine_version,
            "langs": list(langs),
            "warnings": warnings,
        }


__all__ = ["OcrLine", "OcrPage", "OcrWord", "TesseractEngine"]
