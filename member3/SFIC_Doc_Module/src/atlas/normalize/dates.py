"""Deterministic date and timezone normalization with explicit ambiguity tracking.

Implements date normalization supporting ISO formats, free-text dates,
Excel serial date numbers, profile-guided formats, and explicit
ambiguity tracking (e.g. DD/MM vs MM/DD).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import openpyxl.utils.datetime as openpyxl_dt
from dateutil import parser as date_parser


def _is_valid_date(year: int, month: int, day: int) -> bool:
    """Check if given year, month, day form a valid calendar date."""
    try:
        datetime(year, month, day)
        return True
    except (ValueError, OverflowError):
        return False


def _format_time_component(time_str: str) -> str | None:
    """Standardize time string to HH:MM:SS format."""
    cleaned = time_str.strip().upper()
    try:
        if "AM" in cleaned or "PM" in cleaned:
            parts = cleaned.split(":")
            fmt = "%I:%M:%S %p" if len(parts) == 3 else "%I:%M %p"
            dt = datetime.strptime(cleaned, fmt)
        else:
            parts = cleaned.split(":")
            fmt = "%H:%M:%S" if len(parts) == 3 else "%H:%M"
            dt = datetime.strptime(cleaned, fmt)
        return dt.strftime("%H:%M:%S")
    except ValueError:
        return None


def normalize_date(text: str, profile_format: str | None = None) -> dict[str, Any]:
    """Normalize a date string with explicit ambiguity and timezone tracking.

    Rules applied:
    1. Timezone: 'Asia/Kolkata' ONLY when IST or +05:30 is present in the source text; else None.
    2. Profile format: when provided, parsed strictly according to that format.
    3. Excel serial: numeric strings in valid range are converted via openpyxl datetime.
    4. Free text: if day <= 12 and month <= 12 and no profile is provided, and both orders
       yield different valid calendar dates -> ambiguity='dmy_mdy', normalized_iso=None.
    5. Partial dates: e.g. '2023' or '2023-05' -> ambiguity='partial'.
    6. Invalid dates: -> ambiguity='unparseable', normalized_iso=None.

    Args:
        text: Raw date/time text.
        profile_format: Optional strftime format from document profile.

    Returns:
        dict[str, Any]: {
            'original_text': str,
            'normalized_iso': str | None,
            'timezone': str | None,
            'ambiguity': str,
            'notes': str | None
        }
    """
    original = text
    cleaned_input = text.strip() if text else ""

    if not cleaned_input:
        return {
            "original_text": original,
            "normalized_iso": None,
            "timezone": None,
            "ambiguity": "unparseable",
            "notes": "Empty date input",
        }

    # 1. Detect timezone (Asia/Kolkata ONLY when IST or +05:30 is present)
    tz: str | None = None
    if re.search(r"\bIST\b|\+05:?30", cleaned_input):
        tz = "Asia/Kolkata"

    # Strip timezone token for date parsing
    clean_text = re.sub(r"\bIST\b|\+05:?30", "", cleaned_input).strip()

    # 2. Profile-guided parsing
    if profile_format:
        try:
            dt = datetime.strptime(clean_text, profile_format)
            has_time = any(x in profile_format for x in ("%H", "%I", "%M", "%S"))
            iso = dt.strftime("%Y-%m-%dT%H:%M:%S" if has_time else "%Y-%m-%d")
            return {
                "original_text": original,
                "normalized_iso": iso,
                "timezone": tz,
                "ambiguity": "none",
                "notes": None,
            }
        except ValueError:
            return {
                "original_text": original,
                "normalized_iso": None,
                "timezone": tz,
                "ambiguity": "unparseable",
                "notes": f"Failed to parse with profile format '{profile_format}'",
            }

    # 3. Excel serial dates handling (numbers like 44927 or 44927.5)
    try:
        val = float(clean_text)
        # Avoid treating 4-digit years (1900-2099) as Excel serial numbers
        if 1000 <= val <= 100000 and not re.match(r"^(?:19|20)\d{2}$", clean_text):
            dt = openpyxl_dt.from_excel(val)
            iso = dt.strftime("%Y-%m-%d" if val.is_integer() else "%Y-%m-%dT%H:%M:%S")
            return {
                "original_text": original,
                "normalized_iso": iso,
                "timezone": tz,
                "ambiguity": "none",
                "notes": None,
            }
    except (ValueError, OverflowError):
        pass

    # 4. Partial date: 4-digit Year
    if re.match(r"^(?:19|20)\d{2}$", clean_text):
        return {
            "original_text": original,
            "normalized_iso": clean_text,
            "timezone": tz,
            "ambiguity": "partial",
            "notes": None,
        }

    # 5. Partial date: Year-Month
    ym_match = re.match(r"^(?:19|20)\d{2}[-/](?:0[1-9]|1[0-2])$", clean_text)
    if ym_match:
        return {
            "original_text": original,
            "normalized_iso": clean_text.replace("/", "-"),
            "timezone": tz,
            "ambiguity": "partial",
            "notes": None,
        }

    # Extract time component if present at the end
    time_match = re.search(
        r"(?:T|\s+)(\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|am|pm))?)$",
        clean_text,
    )
    time_str: str | None = None
    date_part = clean_text
    if time_match:
        time_str = _format_time_component(time_match.group(1))
        date_part = clean_text[: time_match.start()].strip()

    # 6. ISO date format YYYY-MM-DD or YYYY/MM/DD
    iso_match = re.match(
        r"^(\d{4})[-/.](0[1-9]|1[0-2])[-/.](0[1-9]|[12]\d|3[01])$",
        date_part,
    )
    if iso_match:
        y = int(iso_match.group(1))
        m = int(iso_match.group(2))
        d = int(iso_match.group(3))
        if _is_valid_date(y, m, d):
            iso = f"{y:04d}-{m:02d}-{d:02d}"
            if time_str:
                iso += f"T{time_str}"
            return {
                "original_text": original,
                "normalized_iso": iso,
                "timezone": tz,
                "ambiguity": "none",
                "notes": None,
            }
        return {
            "original_text": original,
            "normalized_iso": None,
            "timezone": tz,
            "ambiguity": "unparseable",
            "notes": "Invalid calendar date",
        }

    # 7. Separator-based numeric date: P1 / P2 / P3
    sep_match = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", date_part)
    if sep_match:
        p1 = int(sep_match.group(1))
        p2 = int(sep_match.group(2))
        p3 = int(sep_match.group(3))
        if p3 < 100:
            p3 += 2000 if p3 < 70 else 1900

        dmy_valid = _is_valid_date(year=p3, month=p2, day=p1)
        mdy_valid = _is_valid_date(year=p3, month=p1, day=p2)

        if dmy_valid and mdy_valid:
            if p1 == p2:
                # Same day and month: unambiguous
                iso = f"{p3:04d}-{p2:02d}-{p1:02d}"
                if time_str:
                    iso += f"T{time_str}"
                return {
                    "original_text": original,
                    "normalized_iso": iso,
                    "timezone": tz,
                    "ambiguity": "none",
                    "notes": None,
                }
            # Ambiguity: both <= 12 and different valid dates
            return {
                "original_text": original,
                "normalized_iso": None,
                "timezone": tz,
                "ambiguity": "dmy_mdy",
                "notes": "Ambiguous date format: day and month both <= 12 without profile",
            }
        elif dmy_valid:
            iso = f"{p3:04d}-{p2:02d}-{p1:02d}"
            if time_str:
                iso += f"T{time_str}"
            return {
                "original_text": original,
                "normalized_iso": iso,
                "timezone": tz,
                "ambiguity": "none",
                "notes": None,
            }
        elif mdy_valid:
            iso = f"{p3:04d}-{p1:02d}-{p2:02d}"
            if time_str:
                iso += f"T{time_str}"
            return {
                "original_text": original,
                "normalized_iso": iso,
                "timezone": tz,
                "ambiguity": "none",
                "notes": None,
            }
        else:
            return {
                "original_text": original,
                "normalized_iso": None,
                "timezone": tz,
                "ambiguity": "unparseable",
                "notes": "Invalid calendar date",
            }

    # 8. Textual month names and dateutil fallback
    try:
        dt = date_parser.parse(clean_text)
        has_time = any(c in clean_text for c in (":", "am", "pm", "AM", "PM")) or time_str is not None
        iso = dt.strftime("%Y-%m-%dT%H:%M:%S" if has_time else "%Y-%m-%d")
        return {
            "original_text": original,
            "normalized_iso": iso,
            "timezone": tz,
            "ambiguity": "none",
            "notes": None,
        }
    except Exception:
        return {
            "original_text": original,
            "normalized_iso": None,
            "timezone": tz,
            "ambiguity": "unparseable",
            "notes": "Could not parse date string",
        }


# Alias for compatibility with tabular parser consumers
parse_date = normalize_date

__all__ = ["normalize_date", "parse_date"]
