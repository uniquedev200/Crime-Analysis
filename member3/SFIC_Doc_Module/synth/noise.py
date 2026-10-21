"""Realistic noise functions for scanned synthetic documents.

Provides slight rotation, salt-and-pepper noise, gaussian blur, and
deliberately confusable digit rendering for OCR testing.
All operations are deterministic given a fixed random seed.
"""

from __future__ import annotations

import random
from typing import Final

from PIL import Image, ImageDraw, ImageFilter

CONFUSABLE_PAIR: Final[tuple[str, str]] = ("8", "3")


def add_slight_rotation(
    image: Image.Image,
    angle_degrees: float = 0.6,
    resample: Image.Resampling = Image.Resampling.BILINEAR,
    fill_color: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Apply slight rotation to simulate scanned paper skew (typically 0.5-1.5 degrees)."""
    return image.rotate(
        angle_degrees,
        resample=resample,
        expand=False,
        fillcolor=fill_color,
    )


def add_salt_and_pepper(
    image: Image.Image,
    amount: float = 0.0015,
    seed: int = 42,
) -> Image.Image:
    """Add deterministic salt-and-pepper noise to simulate photocopy / scan artifacts."""
    if amount <= 0:
        return image.copy()

    rng = random.Random(seed)
    output = image.copy().convert("RGB")
    width, height = output.size
    total_pixels = width * height
    num_noisy_pixels = int(total_pixels * amount)

    draw = ImageDraw.Draw(output)

    # Pepper (dark specks)
    for _ in range(num_noisy_pixels // 2):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        gray = rng.randint(15, 80)
        draw.point((x, y), fill=(gray, gray, gray))

    # Salt (light specks)
    for _ in range(num_noisy_pixels // 2):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        gray = rng.randint(220, 255)
        draw.point((x, y), fill=(gray, gray, gray))

    return output


def add_slight_blur(
    image: Image.Image,
    radius: float = 0.35,
) -> Image.Image:
    """Apply slight Gaussian blur to simulate optical scan soft focus."""
    if radius <= 0:
        return image.copy()
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def substitute_confusable_digit(
    text: str,
    from_digit: str = "8",
    to_digit: str = "3",
    occurrence_index: int = 0,
) -> str:
    """Substitute a confusable digit in a phone or identifier string.

    By default substitutes the specified occurrence of '8' with '3' (or vice versa).
    """
    indices = [i for i, ch in enumerate(text) if ch == from_digit]
    if not indices:
        return text

    target_idx = indices[occurrence_index % len(indices)]
    chars = list(text)
    chars[target_idx] = to_digit
    return "".join(chars)


def apply_digit_occlusion_notch(
    image: Image.Image,
    x: int,
    y: int,
    size: int = 2,
    color: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Draw a microscopic notch on a digit glyph to simulate toner dropout between 8 and 3."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    draw.rectangle([x, y, x + size, y + size], fill=color)
    return out


def apply_scan_noise(
    image: Image.Image,
    angle_degrees: float = 0.5,
    sp_amount: float = 0.0015,
    blur_radius: float = 0.35,
    seed: int = 42,
) -> Image.Image:
    """Composite pipeline applying rotation skew, salt-and-pepper noise, and optical blur."""
    rotated = add_slight_rotation(image, angle_degrees=angle_degrees)
    speckled = add_salt_and_pepper(rotated, amount=sp_amount, seed=seed)
    blurred = add_slight_blur(speckled, radius=blur_radius)
    return blurred


__all__ = [
    "CONFUSABLE_PAIR",
    "add_salt_and_pepper",
    "add_slight_blur",
    "add_slight_rotation",
    "apply_digit_occlusion_notch",
    "apply_scan_noise",
    "substitute_confusable_digit",
]
