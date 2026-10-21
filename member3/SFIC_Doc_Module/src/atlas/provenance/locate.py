"""Location and bounding box computation for verified quotes within document units.

Maps verified quotes to:
- 1-indexed line numbers (line_start, line_end)
- Bounding boxes [x0, y0, x1, y1] at OCR DPI from OCR word boxes when available
- Character spans within normalized page text
"""

from __future__ import annotations

from typing import Any

from atlas.extract.units import Unit
from atlas.provenance.normalize_text import normalize_for_match


def find_all_occurrences(needle: str, haystack: str) -> list[tuple[int, int]]:
    """Return all non-overlapping (start, end) character spans of needle in haystack."""
    if not needle or not haystack:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    needle_len = len(needle)
    while True:
        pos = haystack.find(needle, start)
        if pos == -1:
            break
        spans.append((pos, pos + needle_len))
        start = pos + needle_len
    return spans


def locate_quote_in_unit(
    unit: Unit,
    quote: str,
    occurrence_index: int = 0,
    ocr_page: dict[str, Any] | None = None,
) -> tuple[int | None, int | None, list[float] | None]:
    """Compute line_start, line_end (1-indexed), and bounding box for a quote in a unit.

    Args:
        unit: Source Unit containing raw text and optional line_start/page.
        quote: Quote string to locate.
        occurrence_index: Which occurrence of the quote to locate (0-indexed).
        ocr_page: Optional OCR page dictionary containing lines and word bboxes.

    Returns:
        tuple[int | None, int | None, list[float] | None]:
            (line_start, line_end, bbox_as_floats)
    """
    if not unit.text or not quote:
        base_line = unit.line_start if unit.line_start is not None else 1
        return base_line, base_line, None

    norm_quote = normalize_for_match(quote)
    norm_page = normalize_for_match(unit.text)

    matches = find_all_occurrences(norm_quote, norm_page)
    if not matches:
        base_line = unit.line_start if unit.line_start is not None else 1
        return base_line, base_line, None

    # Select the requested occurrence (or fallback to first)
    target_idx = occurrence_index if 0 <= occurrence_index < len(matches) else 0
    match_start, match_end = matches[target_idx]

    lines = unit.text.splitlines()
    if not lines:
        lines = [unit.text]

    base_line = unit.line_start if unit.line_start is not None else 1

    # Map normalized character offset to 1-indexed lines
    line_start_idx = 1
    line_end_idx = 1

    for k in range(1, len(lines) + 1):
        cum_text = normalize_for_match("\n".join(lines[:k]))
        if len(cum_text) > match_start:
            line_start_idx = k
            break

    for k in range(line_start_idx, len(lines) + 1):
        cum_text = normalize_for_match("\n".join(lines[:k]))
        if len(cum_text) >= match_end:
            line_end_idx = k
            break
    else:
        line_end_idx = len(lines)

    # Convert to document line numbers (e.g. 1-indexed on page, or line_start offset)
    calc_line_start = base_line + (line_start_idx - 1)
    calc_line_end = base_line + (line_end_idx - 1)

    # Compute bounding box if OCR page information is provided
    bbox: list[float] | None = None
    if ocr_page and "lines" in ocr_page and ocr_page["lines"]:
        ocr_lines = ocr_page["lines"]
        # Lines in ocr_page are 0-indexed corresponding to line_start_idx - 1
        cov_start = max(0, line_start_idx - 1)
        cov_end = min(len(ocr_lines), line_end_idx)
        covered_ocr_lines = ocr_lines[cov_start:cov_end]

        matched_boxes: list[list[float]] = []

        for o_line in covered_ocr_lines:
            words = o_line.get("words", [])
            line_matched_words = False
            for w in words:
                w_norm = normalize_for_match(w.get("text", ""))
                if w_norm and w_norm in norm_quote and "bbox" in w and w["bbox"]:
                    b = w["bbox"]
                    matched_boxes.append([float(b[0]), float(b[1]), float(b[2]), float(b[3])])
                    line_matched_words = True

            # If no individual words matched but line has a bbox
            if not line_matched_words and "bbox" in o_line and o_line["bbox"]:
                b = o_line["bbox"]
                matched_boxes.append([float(b[0]), float(b[1]), float(b[2]), float(b[3])])

        if matched_boxes:
            min_x = min(box[0] for box in matched_boxes)
            min_y = min(box[1] for box in matched_boxes)
            max_x = max(box[2] for box in matched_boxes)
            max_y = max(box[3] for box in matched_boxes)
            bbox = [min_x, min_y, max_x, max_y]

    return calc_line_start, calc_line_end, bbox


def locate_all_occurrences(
    unit: Unit,
    quote: str,
    ocr_page: dict[str, Any] | None = None,
) -> list[tuple[int | None, int | None, list[float] | None]]:
    """Locate all occurrences of a quote within a unit.

    Returns:
        List of (line_start, line_end, bbox) tuples for all matches.
    """
    if not unit.text or not quote:
        return []

    norm_quote = normalize_for_match(quote)
    norm_page = normalize_for_match(unit.text)
    matches = find_all_occurrences(norm_quote, norm_page)

    results: list[tuple[int | None, int | None, list[float] | None]] = []
    for idx in range(len(matches)):
        results.append(locate_quote_in_unit(unit, quote, occurrence_index=idx, ocr_page=ocr_page))
    return results


__all__ = ["find_all_occurrences", "locate_all_occurrences", "locate_quote_in_unit"]
