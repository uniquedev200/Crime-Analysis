"""Tabular PDF detector for identifying structured tabular pages.

Identifies pages where >= 30% of lines contain >= 3 aligned numeric columns.
PLAN 5.2: Detect likely tabular PDFs: add tabular_pdf_detected review item
and process as plain text with a warning (never claim row-level parsing).
"""

from __future__ import annotations

import re

# Numeric token pattern: optional currency symbols, sign, numbers with commas/dots/colons/hyphens, optional %
_NUMERIC_TOKEN_PATTERN = re.compile(r"^[₹$€£\.]*(?:Rs\.?)?[-+]?\d[\d,.:/\\-]*%?$")


def _is_numeric_token(tok: str) -> bool:
    """Determine if a token represents a numeric column value."""
    stripped = tok.strip("()[]{},;|\"'")
    if not stripped:
        return False
    return bool(_NUMERIC_TOKEN_PATTERN.match(stripped))


def is_tabular_pdf(text: str) -> bool:
    """Return True if >= 30% of non-empty lines contain >= 3 numeric columns.

    Used to detect CDRs, bank statements, financial tables, etc., that require
    review warnings rather than naive narrative parsing.
    """
    if not text:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    tabular_lines_count = 0
    for line in lines:
        # Split line on whitespace or table delimiters (| or tabs)
        raw_tokens = re.split(r"[\s|\t]+", line)
        tokens = [t for t in raw_tokens if t]
        numeric_count = sum(1 for tok in tokens if _is_numeric_token(tok))
        if numeric_count >= 3:
            tabular_lines_count += 1

    ratio = tabular_lines_count / len(lines)
    return ratio >= 0.30


__all__ = ["is_tabular_pdf"]
