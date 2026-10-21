from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def to_grayscale(image: Image.Image) -> Image.Image:
    """Convert a PIL image to 8-bit grayscale (mode 'L') without mutating original.

    Args:
        image: Source PIL image.

    Returns:
        Grayscale PIL image (mode 'L').
    """
    if image.mode == "L":
        return image.copy()
    return image.convert("L")


def estimate_skew(image: Image.Image) -> float:
    """Estimate skew angle in degrees on a binary image.

    Args:
        image: Binary or grayscale PIL image.

    Returns:
        Estimated skew angle in degrees. Positive indicates counter-clockwise tilt.
    """
    gray = np.array(image.convert("L"))
    if gray.size == 0:
        return 0.0

    mean_val = float(np.mean(gray))
    thresh_type = cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU if mean_val < 128 else cv2.THRESH_BINARY + cv2.THRESH_OTSU
    _, binary = cv2.threshold(gray, 0, 255, thresh_type)

    # Invert binary so text pixels are foreground (255)
    inv = 255 - binary

    if int(cv2.countNonZero(inv)) < 50:
        return 0.0

    # Morphological dilation horizontally to merge character glyphs into line segments
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 3))
    dilated = cv2.dilate(inv, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    angles: list[float] = []
    for c in contours:
        if cv2.contourArea(c) < 100:
            continue
        rect = cv2.minAreaRect(c)
        (w, h) = rect[1]
        if w == 0 or h == 0:
            continue
        a = rect[-1]
        if w < h:
            a = a + 90.0
        while a > 45.0:
            a -= 90.0
        while a < -45.0:
            a += 90.0
        angles.append(a)

    if not angles:
        return 0.0

    # Invert sign to match PIL rotation convention (counter-clockwise is positive)
    med = float(np.median(angles))
    return -med


def deskew(image: Image.Image, angle: float) -> Image.Image:
    """Correct image skew only if 0.5° <= |angle| <= 15°.

    If angle is outside this range, returns the unmodified image.

    Args:
        image: PIL image to deskew.
        angle: Estimated skew angle in degrees.

    Returns:
        Deskewed PIL image or original unmodified image.
    """
    if 0.5 <= abs(angle) <= 15.0:
        fill = 255 if image.mode in ("L", "1") else (255, 255, 255)
        return image.rotate(-angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=fill)
    return image


def preprocess(image: Image.Image) -> Image.Image:
    """Preprocess image for OCR: grayscale -> light denoise -> Otsu binarize -> deskew.

    The original input image is not modified.

    Args:
        image: Input PIL image (color or grayscale).

    Returns:
        Preprocessed binary PIL image (mode 'L').
    """
    # 1. Grayscale
    gray = to_grayscale(image)
    gray_arr = np.array(gray)

    # 2. Light denoise via Gaussian blur
    denoised = cv2.GaussianBlur(gray_arr, (3, 3), 0)

    # 3. Otsu binarize
    _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bin_img = Image.fromarray(binary, mode="L")

    # 4. Deskew
    skew_angle = estimate_skew(bin_img)
    deskewed = deskew(bin_img, skew_angle)

    return deskewed


__all__ = ["deskew", "estimate_skew", "preprocess", "to_grayscale"]
