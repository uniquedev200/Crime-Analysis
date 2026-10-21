"""Unit tests for OCR image preprocessing routines.

Tests deskewing, Otsu binarization, grayscale conversion, and angle bounds.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from atlas.ocr.preprocess import deskew, estimate_skew, preprocess, to_grayscale


@pytest.mark.gate1
def test_preprocess_grayscale() -> None:
    """Verify color images (RGB/RGBA) are converted to 8-bit grayscale mode 'L'."""
    # 1. RGB color image
    rgb_img = Image.new("RGB", (100, 100), color=(255, 128, 64))
    gray_result = to_grayscale(rgb_img)
    assert gray_result.mode == "L"
    assert len(gray_result.getbands()) == 1

    # 2. RGBA color image
    rgba_img = Image.new("RGBA", (100, 100), color=(100, 150, 200, 255))
    gray_from_rgba = to_grayscale(rgba_img)
    assert gray_from_rgba.mode == "L"

    # 3. Full preprocess pipeline output is grayscale mode 'L'
    processed = preprocess(rgb_img)
    assert processed.mode == "L"
    assert len(processed.getbands()) == 1


@pytest.mark.gate1
def test_deskew_bounds() -> None:
    """Verify deskew correction bounds: 0.5° <= |angle| <= 15°.

    - angle < 0.5°: no correction (unmodified)
    - 0.5° <= |angle| <= 15°: corrected
    - |angle| > 15°: no correction (unmodified)
    """
    img = Image.new("L", (200, 100), color=255)
    draw = ImageDraw.Draw(img)
    draw.line([(20, 50), (180, 50)], fill=0, width=3)

    # 1. |angle| < 0.5° -> no correction
    assert deskew(img, 0.0) is img
    assert deskew(img, 0.2) is img
    assert deskew(img, 0.49) is img
    assert deskew(img, -0.3) is img
    assert deskew(img, -0.49) is img

    # 2. 0.5° <= |angle| <= 15° -> corrected (returns rotated image)
    corrected_pos = deskew(img, 0.5)
    assert corrected_pos is not img
    assert corrected_pos.size == img.size

    corrected_mid = deskew(img, 5.0)
    assert corrected_mid is not img
    # Pixels should have changed
    assert np.any(np.array(corrected_mid) != np.array(img))

    corrected_neg = deskew(img, -5.0)
    assert corrected_neg is not img
    assert np.any(np.array(corrected_neg) != np.array(img))

    corrected_max = deskew(img, 15.0)
    assert corrected_max is not img

    corrected_neg_max = deskew(img, -15.0)
    assert corrected_neg_max is not img

    # 3. |angle| > 15° -> no correction
    assert deskew(img, 15.01) is img
    assert deskew(img, 20.0) is img
    assert deskew(img, 45.0) is img
    assert deskew(img, -15.01) is img
    assert deskew(img, -30.0) is img


@pytest.mark.gate1
def test_estimate_skew_horizontal() -> None:
    """Verify estimate_skew returns 0.0 or near zero on upright horizontal lines."""
    img = Image.new("L", (400, 200), color=255)
    draw = ImageDraw.Draw(img)
    for y in [40, 80, 120, 160]:
        draw.line([(30, y), (370, y)], fill=0, width=4)

    angle = estimate_skew(img)
    assert abs(angle) < 0.5


@pytest.mark.gate1
def test_estimate_skew_tilted() -> None:
    """Verify estimate_skew detects tilt accurately on rendered lines."""
    base = Image.new("L", (600, 400), color=255)
    draw = ImageDraw.Draw(base)
    for y in range(50, 350, 40):
        draw.line([(50, y), (550, y)], fill=0, width=5)

    # Rotate by 4.0 degrees
    rotated = base.rotate(4.0, resample=Image.Resampling.BICUBIC, fillcolor=255)
    detected_angle = estimate_skew(rotated)

    # Should detect approximately 4.0 degrees within 0.5 degree margin
    assert abs(detected_angle - 4.0) < 0.6

    # Rotate by -3.0 degrees
    rotated_neg = base.rotate(-3.0, resample=Image.Resampling.BICUBIC, fillcolor=255)
    detected_neg = estimate_skew(rotated_neg)
    assert abs(detected_neg - (-3.0)) < 0.6


@pytest.mark.gate1
def test_estimate_skew_blank_image() -> None:
    """Verify estimate_skew returns 0.0 on blank or solid images."""
    blank = Image.new("L", (100, 100), color=255)
    assert estimate_skew(blank) == 0.0

    solid_black = Image.new("L", (100, 100), color=0)
    assert estimate_skew(solid_black) == 0.0


@pytest.mark.gate1
def test_preprocess_unmodified_render() -> None:
    """Verify preprocess leaves the input PIL image object intact and unmodified."""
    img = Image.new("RGB", (200, 200), color=(200, 100, 50))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 150, 150], fill=(10, 20, 30))

    original_bytes = img.tobytes()
    original_size = img.size
    original_mode = img.mode

    result = preprocess(img)

    # Input image was not mutated
    assert img.tobytes() == original_bytes
    assert img.size == original_size
    assert img.mode == original_mode

    # Output is a distinct object in mode 'L'
    assert result is not img
    assert result.mode == "L"
