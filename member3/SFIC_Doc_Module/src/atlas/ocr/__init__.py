"""OCR package for ATLAS Dev 3 pipeline.

Provides preprocessing routines (grayscale, denoise, Otsu binarization, deskew),
Tesseract and PaddleOCR engine adapters, and language pack verification.
"""

from __future__ import annotations

from atlas.ocr.langs import check_languages, get_available_languages
from atlas.ocr.paddle import PaddleEngine
from atlas.ocr.preprocess import deskew, estimate_skew, preprocess, to_grayscale
from atlas.ocr.tesseract import OcrLine, OcrPage, OcrWord, TesseractEngine

__all__ = [
    "OcrLine",
    "OcrPage",
    "OcrWord",
    "PaddleEngine",
    "TesseractEngine",
    "check_languages",
    "deskew",
    "estimate_skew",
    "get_available_languages",
    "preprocess",
    "to_grayscale",
]
