"""Text normalization helpers for exact and robust quote matching.

Implements Section 5.4 specification:
- Unicode NFC normalization
- Zero-width character removal and NBSP replacement
- Hyphen+newline joining (including line breaks)
- Whitespace collapsing and stripping
- Preservation of case and punctuation
"""

from __future__ import annotations

import re
import unicodedata

# Zero-width spaces, joiners, and BOM
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

# Hyphen followed by optional whitespace and newline
_HYPHEN_NEWLINE_RE = re.compile(r"-[ \t]*\r?\n")

# Multiple whitespace characters (including newlines and tabs)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_match(s: str) -> str:
    """Normalize text for quote verification substring matching.

    Rules applied in order:
    1. Unicode NFC normalization.
    2. Replace NBSP (\\u00a0) with a space.
    3. Remove zero-width characters (\\u200b, \\u200c, \\u200d, \\ufeff).
    4. Join hyphen+newline: '-[ \\t]*\\r?\\n' -> ''.
    5. Collapse all whitespace sequences into a single ASCII space.
    6. Strip leading and trailing whitespace.

    Note:
    - Case is NOT folded.
    - Punctuation is NOT stripped.

    Args:
        s: Raw input string.

    Returns:
        Normalized string for substring search.
    """
    if not s:
        return ""

    # 1. Unicode NFC normalization
    res = unicodedata.normalize("NFC", s)

    # 2. Replace NBSP with space
    res = res.replace("\u00a0", " ")

    # 3. Remove zero-width characters
    res = _ZERO_WIDTH_RE.sub("", res)

    # 4. Join hyphen+newline
    res = _HYPHEN_NEWLINE_RE.sub("", res)

    # 5. Collapse all whitespace to a single space
    res = _WHITESPACE_RE.sub(" ", res)

    # 6. Strip leading and trailing whitespace
    return res.strip()


__all__ = ["normalize_for_match"]
