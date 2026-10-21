"""Normalization and validation package for ATLAS Dev 3.

Provides deterministic normalization for identifiers (phones, IMEI,
vehicle plates, account numbers), personal names, and dates/timezones.
"""

from __future__ import annotations

from atlas.normalize.dates import normalize_date, parse_date
from atlas.normalize.identifiers import (
    detect_identifiers,
    normalize_account,
    normalize_phone,
    normalize_vehicle,
    validate_imei,
)
from atlas.normalize.names import (
    PersonNameFilter,
    is_valid_person_name,
    load_person_name_filter,
    name_key,
    parse_patronymic,
    strip_honorifics,
)

__all__ = [
    "PersonNameFilter",
    "detect_identifiers",
    "is_valid_person_name",
    "load_person_name_filter",
    "name_key",
    "normalize_account",
    "normalize_date",
    "normalize_phone",
    "normalize_vehicle",
    "parse_date",
    "parse_patronymic",
    "strip_honorifics",
    "validate_imei",
]
