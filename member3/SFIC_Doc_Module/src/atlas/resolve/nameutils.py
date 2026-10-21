"""Name normalization and fuzzy similarity utilities for entity resolution.

Implements token_sort_ratio, Jaro-Winkler similarity, honorific stripping,
and name key matching using rapidfuzz and atlas.normalize.names.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

import rapidfuzz.distance.JaroWinkler as jw
import rapidfuzz.fuzz as fuzz

from atlas.normalize.names import name_key as normalize_name_key
from atlas.normalize.names import strip_honorifics

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_NON_ALNUM_RE: Final[re.Pattern[str]] = re.compile(r"[^\w\s]", re.UNICODE)


def clean_name(name: str) -> str:
    """Strip honorifics, collapse whitespace, and trim a personal name."""
    if not name:
        return ""
    stripped = strip_honorifics(name)
    normalized = unicodedata.normalize("NFC", stripped)
    collapsed = _WHITESPACE_RE.sub(" ", normalized).strip()
    return collapsed


def name_key(name: str) -> str:
    """Return deterministic normalized key for candidate name matching."""
    return normalize_name_key(name)


def get_name_tokens(name: str) -> list[str]:
    """Tokenize a name into cleaned alnum tokens."""
    cleaned = clean_name(name)
    cleaned_no_punct = _NON_ALNUM_RE.sub(" ", cleaned)
    tokens = [t for t in _WHITESPACE_RE.split(cleaned_no_punct) if t]
    return tokens


def is_initials_compatible(name1: str, name2: str) -> bool:
    """Check if one name is an initial-abbreviated variant of another.

    E.g. 'V. Singh' vs 'Vikram Singh', or 'R. K. Sharma' vs 'Rajesh Kumar Sharma'.
    """
    toks1 = get_name_tokens(name1.lower())
    toks2 = get_name_tokens(name2.lower())
    if not toks1 or not toks2:
        return False

    # Must share at least one non-initial token (e.g. surname)
    surnames1 = [t for t in toks1 if len(t) > 1]
    surnames2 = [t for t in toks2 if len(t) > 1]
    if not surnames1 or not surnames2:
        return False
    if surnames1[-1] != surnames2[-1]:
        return False

    # Check that initials align
    initials1 = [t[0] for t in toks1]
    initials2 = [t[0] for t in toks2]
    return initials1 == initials2


def name_similarity_scores(name1: str, name2: str) -> dict[str, float]:
    """Calculate token_sort_ratio, Jaro-Winkler, and composite similarity.

    Both metrics are returned on a [0.0, 1.0] scale.
    Composite is the maximum of token_sort_ratio and Jaro-Winkler,
    with an initials boost if compatible.
    """
    clean1 = clean_name(name1)
    clean2 = clean_name(name2)
    if not clean1 or not clean2:
        return {"token_sort_ratio": 0.0, "jaro_winkler": 0.0, "composite": 0.0}

    # Direct string comparison
    tsr = float(fuzz.token_sort_ratio(clean1, clean2)) / 100.0
    jw_sim = float(jw.similarity(clean1.lower(), clean2.lower()))

    # Also compute on name_key representations
    key1 = name_key(clean1)
    key2 = name_key(clean2)
    if key1 and key2:
        key_tsr = float(fuzz.token_sort_ratio(key1, key2)) / 100.0
        key_jw = float(jw.similarity(key1, key2))
        tsr = max(tsr, key_tsr)
        jw_sim = max(jw_sim, key_jw)

    composite = max(tsr, jw_sim)

    # If initials match (e.g. V. Singh vs Vikram Singh) and score is moderate, boost
    if composite < 0.85 and is_initials_compatible(clean1, clean2):
        composite = max(composite, 0.80)

    return {
        "token_sort_ratio": round(tsr, 4),
        "jaro_winkler": round(jw_sim, 4),
        "composite": round(composite, 4),
    }


def are_names_compatible(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Return True if composite name similarity meets or exceeds threshold."""
    scores = name_similarity_scores(name1, name2)
    return scores["composite"] >= threshold


__all__ = [
    "are_names_compatible",
    "clean_name",
    "get_name_tokens",
    "is_initials_compatible",
    "name_key",
    "name_similarity_scores",
]
