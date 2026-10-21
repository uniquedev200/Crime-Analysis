"""Tabular data ingestion and parsing package for ATLAS Dev 3.

Provides deterministic CSV/XLSX readers, profile-based schema detection,
CDR and bank statement parsers, date handling wrappers, and mapping suggestions.
"""

from __future__ import annotations

from atlas.tabular.anpr import parse_anpr
from atlas.tabular.bank import parse_amount, parse_bank
from atlas.tabular.cdr import parse_cdr
from atlas.tabular.csv_reader import read_csv, sniff_delimiter
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.mapping_suggest import suggest_mapping
from atlas.tabular.profiles import (
    create_mapping_unconfirmed_review,
    detect_profile,
    load_profile,
    normalize_header,
)
from atlas.tabular.tower import parse_tower
from atlas.tabular.xlsx_reader import read_xlsx

__all__ = [
    "create_mapping_unconfirmed_review",
    "detect_profile",
    "load_profile",
    "normalize_header",
    "parse_amount",
    "parse_anpr",
    "parse_bank",
    "parse_cdr",
    "parse_date_with_profile",
    "parse_tower",
    "read_csv",
    "read_xlsx",
    "sniff_delimiter",
    "suggest_mapping",
]
