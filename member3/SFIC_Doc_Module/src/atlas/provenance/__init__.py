"""Provenance and quote verification package for ATLAS Dev 3."""

from __future__ import annotations

from atlas.provenance.chunking import chunk_units, split_large_unit
from atlas.provenance.locate import find_all_occurrences, locate_all_occurrences, locate_quote_in_unit
from atlas.provenance.normalize_text import normalize_for_match
from atlas.provenance.verify import verify_model_output

__all__ = [
    "chunk_units",
    "find_all_occurrences",
    "locate_all_occurrences",
    "locate_quote_in_unit",
    "normalize_for_match",
    "split_large_unit",
    "verify_model_output",
]
