"""Unit tests for Tesseract OCR engine, language verification, and output structures.

Tests mock output mapping, -1 confidence handling, missing language pack error,
raw text preservation, real Tesseract execution, and PaddleOCR adapter.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from atlas.config import get_settings
from atlas.errors import OcrLanguageUnavailable
from atlas.ocr.langs import check_languages
from atlas.ocr.paddle import PaddleEngine
from atlas.ocr.tesseract import TesseractEngine
from atlas.ports.ocr import OcrEnginePort


@pytest.mark.gate1
def test_ocr_port_conformance() -> None:
    """Verify TesseractEngine implements OcrEnginePort protocol."""
    engine = TesseractEngine()
    assert isinstance(engine, OcrEnginePort)
    assert engine.engine_name == "tesseract"
    assert isinstance(engine.engine_version, str)


@pytest.mark.gate1
def test_tesseract_mock_output() -> None:
    """Verify mock pytesseract.image_to_data produces correct OcrPage structure."""
    mock_data = {
        "level": [1, 2, 3, 4, 5, 5, 4, 5],
        "page_num": [1, 1, 1, 1, 1, 1, 1, 1],
        "block_num": [0, 1, 1, 1, 1, 1, 1, 1],
        "par_num": [0, 0, 1, 1, 1, 1, 1, 1],
        "line_num": [0, 0, 0, 1, 1, 1, 2, 2],
        "word_num": [0, 0, 0, 0, 1, 2, 0, 1],
        "left": [0, 10, 10, 10, 10, 80, 10, 10],
        "top": [0, 10, 10, 10, 10, 10, 40, 40],
        "width": [500, 400, 400, 200, 60, 70, 100, 100],
        "height": [500, 100, 100, 25, 20, 20, 25, 25],
        "conf": [-1, -1, -1, -1, 95.0, 90.0, -1, 85.0],
        "text": ["", "", "", "", "First", "Information", "", "Report"],
    }

    engine = TesseractEngine(validate_langs=False)
    img = Image.new("RGB", (300, 200), color=(255, 255, 255))

    with (
        patch("pytesseract.image_to_data", return_value=mock_data),
        patch("pytesseract.get_tesseract_version", return_value="5.3.0"),
    ):
        result = engine.recognize(img, langs=["eng"])

    assert result["engine"] == "tesseract"
    assert result["version"] == "5.3.0"
    assert result["langs"] == ["eng"]
    assert result["raw_text"] == "First Information\nReport"
    assert len(result["lines"]) == 2

    # Line 1 assertions
    line1 = result["lines"][0]
    assert line1["text"] == "First Information"
    assert len(line1["words"]) == 2
    assert line1["words"][0]["text"] == "First"
    assert line1["words"][0]["conf"] == 95.0
    assert line1["words"][0]["bbox"] == [10, 10, 70, 30]
    assert line1["words"][1]["text"] == "Information"
    assert line1["words"][1]["conf"] == 90.0
    assert line1["words"][1]["bbox"] == [80, 10, 150, 30]
    assert line1["bbox"] == [10, 10, 150, 30]
    assert line1["conf_mean"] == 92.5

    # Line 2 assertions
    line2 = result["lines"][1]
    assert line2["text"] == "Report"
    assert len(line2["words"]) == 1
    assert line2["words"][0]["text"] == "Report"
    assert line2["words"][0]["conf"] == 85.0
    assert line2["bbox"] == [10, 40, 110, 65]
    assert line2["conf_mean"] == 85.0


@pytest.mark.gate1
def test_conf_minus_one() -> None:
    """Verify confidence score of -1 is mapped to None and never fabricated."""
    mock_data = {
        "level": [5, 5],
        "page_num": [1, 1],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
        "word_num": [1, 2],
        "left": [10, 60],
        "top": [10, 10],
        "width": [40, 50],
        "height": [20, 20],
        "conf": [-1, "-1"],
        "text": ["Unknown", "Word"],
    }

    engine = TesseractEngine(validate_langs=False)
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))

    with patch("pytesseract.image_to_data", return_value=mock_data):
        result = engine.recognize(img, langs=["eng"])

    assert len(result["lines"]) == 1
    words = result["lines"][0]["words"]
    assert words[0]["conf"] is None
    assert words[1]["conf"] is None
    # No valid word confidences -> line conf_mean must be None (never fabricated)
    assert result["lines"][0]["conf_mean"] is None


@pytest.mark.gate1
def test_missing_lang_pack() -> None:
    """Verify requesting an unavailable language pack raises OcrLanguageUnavailable."""
    with patch("atlas.ocr.langs.get_available_languages", return_value={"eng", "osd"}):
        # 1. Missing language raises OcrLanguageUnavailable
        with pytest.raises(OcrLanguageUnavailable) as exc_info:
            check_languages(["tam"], tesseract_cmd="dummy_tesseract")
        assert exc_info.value.lang == "tam"
        assert "tam" in str(exc_info.value)

        # 2. Compound string with missing language
        with pytest.raises(OcrLanguageUnavailable) as exc_info2:
            check_languages(["eng+hin"], tesseract_cmd="dummy_tesseract")
        assert exc_info2.value.lang == "hin"

        # 3. Available languages succeed without raising
        check_languages(["eng"], tesseract_cmd="dummy_tesseract")


@pytest.mark.gate1
def test_get_available_languages_parsing() -> None:
    """Verify get_available_languages parses stdout from tesseract --list-langs."""
    from subprocess import CompletedProcess

    from atlas.ocr.langs import get_available_languages

    # 1. Successful parse of standard output
    mock_stdout = "List of available languages (3):\neng\nosd\nhin\n"
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("subprocess.run", return_value=CompletedProcess(["tess", "--list-langs"], 0, stdout=mock_stdout)),
    ):
        langs = get_available_languages("dummy_tesseract")
        assert langs == {"eng", "osd", "hin"}

    # 2. Subprocess failure returns empty set
    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch("subprocess.run", return_value=CompletedProcess(["tess", "--list-langs"], 1, stdout="", stderr="Error")),
    ):
        assert get_available_languages("dummy_tesseract") == set()

    # 3. Binary not found returns empty set
    with (
        patch("pathlib.Path.is_file", return_value=False),
        patch("shutil.which", return_value=None),
    ):
        assert get_available_languages("nonexistent_binary") == set()


@pytest.mark.gate1
def test_raw_text_preserved() -> None:
    """Verify OCR raw text is preserved exactly as returned with no cleaning or modification."""
    uncleaned_words = ["FIR/2024-A!", "MoBiLe: +91-98765-43210", "1nv3st1gat10n", "₹50,000/-"]
    mock_data = {
        "level": [5] * len(uncleaned_words),
        "page_num": [1] * len(uncleaned_words),
        "block_num": [1] * len(uncleaned_words),
        "par_num": [1] * len(uncleaned_words),
        "line_num": [1, 1, 2, 2],
        "word_num": [1, 2, 1, 2],
        "left": [10, 80, 10, 80],
        "top": [10, 10, 40, 40],
        "width": [50, 60, 50, 60],
        "height": [20, 20, 20, 20],
        "conf": [90.0] * len(uncleaned_words),
        "text": uncleaned_words,
    }

    engine = TesseractEngine(validate_langs=False)
    img = Image.new("RGB", (300, 150), color=(255, 255, 255))

    with patch("pytesseract.image_to_data", return_value=mock_data):
        result = engine.recognize(img, langs=["eng"])

    # Raw text must contain the exact uncleaned strings with no lowercasing or symbol stripping
    raw = result["raw_text"]
    for word in uncleaned_words:
        assert word in raw, f"Expected '{word}' to be preserved in raw text, got: {raw}"


@pytest.mark.gate1
@pytest.mark.needs_tesseract
def test_real_tesseract() -> None:
    """Run real Tesseract engine on an independently rendered clean test page.

    Renders a page using synth/fonts/DejaVuSans.ttf with known text and asserts
    that real OCR extracts the known words accurately.
    Mandatory when ATLAS_REQUIRE_TESSERACT=true.
    """
    settings = get_settings()
    tesseract_binary = settings.TESSERACT_CMD

    # Check if binary exists
    binary_found = Path(tesseract_binary).is_file()
    if not binary_found:
        import shutil

        which_tess = shutil.which("tesseract")
        if which_tess:
            binary_found = True
            tesseract_binary = which_tess

    if not binary_found:
        if settings.ATLAS_REQUIRE_TESSERACT:
            pytest.fail(
                f"Tesseract binary not found at '{settings.TESSERACT_CMD}', "
                "but ATLAS_REQUIRE_TESSERACT=true. Install Tesseract to satisfy Gate 1."
            )
        else:
            pytest.skip(f"Tesseract binary not found at '{settings.TESSERACT_CMD}' and ATLAS_REQUIRE_TESSERACT=false")

    # B1 renders its OWN test page using the vendored font
    font_path = Path("synth/fonts/DejaVuSans.ttf")
    assert font_path.is_file(), f"Vendored font not found at {font_path}"

    font = ImageFont.truetype(str(font_path), 28)
    img = Image.new("RGB", (900, 500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    known_phrases = [
        "POLICE DEPARTMENT INVESTIGATION",
        "Case Number: FIR-2024-98765",
        "Complainant: Rajesh Kumar",
        "Suspect: Amit Sharma",
        "Phone: 9876543210",
    ]

    for idx, phrase in enumerate(known_phrases):
        draw.text((50, 40 + idx * 80), phrase, fill=(0, 0, 0), font=font)

    engine = TesseractEngine(tesseract_cmd=tesseract_binary)
    result = engine.recognize(img, langs=["eng"])

    assert result["engine"] == "tesseract"
    assert len(result["lines"]) > 0

    extracted_text = result["raw_text"]
    assert "POLICE" in extracted_text
    assert "Rajesh" in extracted_text
    assert "9876543210" in extracted_text


@pytest.mark.gate1
@pytest.mark.optional
def test_paddle_adapter_optional() -> None:
    """Verify PaddleEngine port implementation and import guard.

    Marked optional so that Gate 1 passes when PaddleOCR extra is not installed.
    """
    try:
        engine = PaddleEngine()
        assert isinstance(engine, OcrEnginePort)
        assert engine.engine_name == "paddle"
    except ImportError as exc:
        # Paddle is optional; if missing, verify actionable error message
        assert "PaddleOCR is not available" in str(exc)


@pytest.mark.gate1
def test_ocr_benchmark_cer_and_tokens() -> None:
    """Verify OCR benchmark calculation of CER and token exact matching."""
    from scripts.ocr_benchmark import compute_cer, evaluate_tokens

    # Character Error Rate (CER)
    assert compute_cer("hello world", "hello world") == 0.0
    assert compute_cer("abc", "abd") == pytest.approx(1.0 / 3.0)
    assert compute_cer("", "") == 0.0
    assert compute_cer("abc", "") == 1.0

    # Token exact-match evaluation
    tokens = ["9876543210", "356938035643809", "1234567890"]
    ocr_text = "Phone number is 9876543210 and account 1234567890."
    eval_res = evaluate_tokens(tokens, ocr_text)

    assert eval_res["total"] == 3
    assert eval_res["matched"] == 2
    assert eval_res["accuracy"] == pytest.approx(2.0 / 3.0)
    assert "9876543210" in eval_res["matched_tokens"]
    assert "1234567890" in eval_res["matched_tokens"]
    assert "356938035643809" in eval_res["missing_tokens"]
