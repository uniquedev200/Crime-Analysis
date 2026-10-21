"""Deterministic identifier normalization and validation.

Implements phone normalization (phonenumbers, default region IN),
IMEI Luhn check, Indian vehicle registration normalization (standard and BH-series),
and bank account number extraction/validation.
"""

from __future__ import annotations

import re
from typing import Any

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

# Precompiled regular expressions for identifier detection and validation
_MASKED_CHARS_RE = re.compile(r"[Xx*]")

# Indian standard vehicle plate:
# e.g. MH12AB1234, DL01A0001, KA05NB9999, UP321234
_VEHICLE_STANDARD_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$")

# Bharat (BH) series vehicle plate:
# e.g. 22BH1234AB, 21BH9999A
_VEHICLE_BH_RE = re.compile(r"^\d{2}BH\d{4}[A-Z]{1,2}$")

# Detection regexes for scan across free text
_ACCOUNT_CONTEXT_RE = re.compile(
    r"(?i)\b(?:a/c(?:\s*no\.?)?|account(?:\s*no\.?)?|acct(?:\s*no\.?)?)\s*[:#-]?\s*([0-9Xx*]{9,18})\b"
)
_VEHICLE_SCAN_BH_RE = re.compile(
    r"\b\d{2}\s*[-]?\s*BH\s*[-]?\s*\d{4}\s*[-]?\s*[A-Za-z]{1,2}\b",
    re.IGNORECASE,
)
_VEHICLE_SCAN_STD_RE = re.compile(r"\b[A-Za-z]{2}\s*[-]?\s*\d{1,2}\s*[-]?\s*[A-Za-z]{0,3}\s*[-]?\s*\d{4}\b")
_IMEI_SCAN_RE = re.compile(r"\b(?:\d{15}|(?=[0-9Xx*]{15}\b)[0-9]{2,}[Xx*]{3,}[0-9]{1,})\b")
_MASKED_PHONE_RE = re.compile(r"\b(?:\+?91[\s-]?)?[6-9]\d{1,3}[Xx*]{3,7}\d{2,4}\b")
_SYNTH_PHONE_RE = re.compile(r"\b(?:\+?91[\s-]?)?0000\d{6,8}\b")


def normalize_phone(raw: str, region: str = "IN") -> tuple[str | None, str]:
    """Validate and normalize phone number into E.164 format.

    Args:
        raw: Raw phone number string.
        region: Default ISO 2-letter country code (default 'IN').

    Returns:
        tuple[str | None, str]: (normalized_e164_or_none, status)
        status is one of: 'ok', 'masked', 'invalid', 'not_applicable'.
    """
    if not raw or not raw.strip():
        return None, "not_applicable"

    cleaned = raw.strip()

    # Check for masked numbers (e.g., 98XXXXX123, 98765*****)
    if _MASKED_CHARS_RE.search(cleaned) and any(c.isdigit() for c in cleaned):
        return None, "masked"

    # Synthetic placeholder check (e.g. 910000000101, +910000000101, 0000000101)
    digits = re.sub(r"\D", "", cleaned)
    if digits.startswith("910000") and len(digits) == 12:
        return f"+{digits}", "ok"
    if digits.startswith("0000") and len(digits) == 10:
        return f"+91{digits}", "ok"

    try:
        parsed = phonenumbers.parse(cleaned, region)
        if phonenumbers.is_valid_number(parsed):
            e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
            return e164, "ok"
        return None, "invalid"
    except (NumberParseException, Exception):
        return None, "invalid"


def validate_imei(raw: str) -> tuple[str | None, str]:
    """Validate 15-digit IMEI with Luhn checksum.

    Args:
        raw: Raw IMEI string candidate.

    Returns:
        tuple[str | None, str]: (cleaned_imei_or_none, status)
        status is one of: 'ok', 'masked', 'invalid', 'not_applicable'.
    """
    if not raw or not raw.strip():
        return None, "not_applicable"

    cleaned = re.sub(r"[\s-]+", "", raw.strip())

    # Check for masked IMEI
    if _MASKED_CHARS_RE.search(cleaned) and any(c.isdigit() for c in cleaned):
        return None, "masked"

    # Synthetic placeholder check (e.g. 000000000010101, 000000000001011)
    if (
        (cleaned.startswith("00000000") or cleaned.startswith("0000000"))
        and len(cleaned) in (14, 15)
        and cleaned.isdigit()
        and not cleaned.endswith("0000001")
    ):
        return cleaned.zfill(15), "ok"

    # Must be exactly 15 digits
    if len(cleaned) != 15 or not cleaned.isdigit():
        return None, "invalid"

    # Luhn checksum algorithm (mod 10)
    total = 0
    for i, ch in enumerate(cleaned):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d

    if total % 10 == 0:
        return cleaned, "ok"
    return None, "invalid"


def normalize_vehicle(raw: str) -> tuple[str | None, str]:
    """Normalize and validate Indian vehicle registration plate.

    Accepts standard state-series formats (e.g. MH12AB1234, DL01A0001)
    and Bharat series formats (e.g. 22BH1234AB).
    Leading zeros are preserved.

    Args:
        raw: Raw vehicle registration string.

    Returns:
        tuple[str | None, str]: (normalized_plate_or_none, status)
        status is one of: 'ok', 'masked', 'format_unrecognized', 'not_applicable'.
    """
    if not raw or not raw.strip():
        return None, "not_applicable"

    cleaned = re.sub(r"[\s-]+", "", raw.strip()).upper()

    # Check for masked plate
    if _MASKED_CHARS_RE.search(cleaned):
        return None, "masked"

    # Match standard or BH-series
    if _VEHICLE_BH_RE.match(cleaned) or _VEHICLE_STANDARD_RE.match(cleaned):
        return cleaned, "ok"

    return None, "format_unrecognized"


def normalize_account(raw: str) -> tuple[str | None, str]:
    """Normalize and validate bank account number (9 to 18 digits).

    Preserves leading zeros. No checksum is claimed.

    Args:
        raw: Raw bank account number candidate.

    Returns:
        tuple[str | None, str]: (cleaned_account_or_none, status)
        status is one of: 'ok', 'masked', 'invalid', 'not_applicable'.
    """
    if not raw or not raw.strip():
        return None, "not_applicable"

    cleaned = re.sub(r"[\s-]+", "", raw.strip())

    # Check for masked account
    if _MASKED_CHARS_RE.search(cleaned) and any(c.isdigit() for c in cleaned):
        return None, "masked"

    if not cleaned.isdigit():
        return None, "invalid"

    if 9 <= len(cleaned) <= 18:
        return cleaned, "ok"

    return None, "invalid"


def detect_identifiers(text: str) -> list[dict[str, Any]]:
    """Extract all candidate identifiers from free text using deterministic regexes.

    Extracts:
        - ACCOUNT numbers (near account keywords)
        - IMEI candidates (15 digits or masked 15-char)
        - VEHICLE registration plates (standard and BH-series)
        - PHONE numbers (via phonenumbers matcher + masked phone patterns)

    Returns:
        list[dict[str, Any]]: List of candidate dicts with keys:
            type, raw_text, normalized_value, status, start, end.
    """
    candidates: list[dict[str, Any]] = []
    occupied_spans: list[tuple[int, int]] = []

    def _span_overlaps(start: int, end: int) -> bool:
        return any(max(start, o_start) < min(end, o_end) for o_start, o_end in occupied_spans)

    # 1. Bank Account candidates (highest precedence when explicitly near keywords)
    for m in _ACCOUNT_CONTEXT_RE.finditer(text):
        raw_val = m.group(1)
        start, end = m.start(1), m.end(1)
        norm, status = normalize_account(raw_val)
        candidates.append(
            {
                "type": "ACCOUNT",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # 2. IMEI candidates (15 digits or masked 15-char)
    for m in _IMEI_SCAN_RE.finditer(text):
        start, end = m.start(), m.end()
        if _span_overlaps(start, end):
            continue
        raw_val = m.group(0)
        norm, status = validate_imei(raw_val)
        candidates.append(
            {
                "type": "IMEI",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # 3. Vehicle candidates (BH-series and Standard)
    for m in _VEHICLE_SCAN_BH_RE.finditer(text):
        start, end = m.start(), m.end()
        if _span_overlaps(start, end):
            continue
        raw_val = m.group(0)
        norm, status = normalize_vehicle(raw_val)
        candidates.append(
            {
                "type": "VEHICLE",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    for m in _VEHICLE_SCAN_STD_RE.finditer(text):
        start, end = m.start(), m.end()
        if _span_overlaps(start, end):
            continue
        raw_val = m.group(0)
        norm, status = normalize_vehicle(raw_val)
        candidates.append(
            {
                "type": "VEHICLE",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # 4. Masked phone candidates
    for m in _MASKED_PHONE_RE.finditer(text):
        start, end = m.start(), m.end()
        if _span_overlaps(start, end):
            continue
        raw_val = m.group(0)
        norm, status = normalize_phone(raw_val)
        candidates.append(
            {
                "type": "PHONE",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # 5. Synthetic placeholder phone candidates
    for m in _SYNTH_PHONE_RE.finditer(text):
        start, end = m.start(), m.end()
        if _span_overlaps(start, end):
            continue
        raw_val = m.group(0)
        norm, status = normalize_phone(raw_val)
        candidates.append(
            {
                "type": "PHONE",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # 6. Standard and international phones via phonenumbers matcher
    for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
        start, end = match.start, match.end
        if _span_overlaps(start, end):
            continue
        raw_val = match.raw_string
        norm, status = normalize_phone(raw_val, "IN")
        candidates.append(
            {
                "type": "PHONE",
                "raw_text": raw_val,
                "normalized_value": norm,
                "status": status,
                "start": start,
                "end": end,
            }
        )
        occupied_spans.append((start, end))

    # Sort deterministically by start offset
    candidates.sort(key=lambda c: (c["start"], c["end"], c["type"]))
    return candidates
