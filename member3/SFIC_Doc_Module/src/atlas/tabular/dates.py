"""Date and timezone parsing helpers for tabular data.

Implements PLAN.md section 5.8:
- Original text preserved.
- Profile-directed format parsing.
- Excel serial date parsing (via openpyxl/dateutil).
- Ambiguity classification (dmy_mdy when day <= 12 and month <= 12 without profile).
- Timezone assigned only when explicitly stated (Asia/Kolkata for IST/+05:30, UTC for UTC/Z, else None).
"""

from __future__ import annotations

import datetime
import importlib
import re
from typing import Any

from dateutil import parser as dateutil_parser
from openpyxl.utils.datetime import from_excel

from atlas.contracts.enums import TimeAmbiguity

try:
    _norm_mod: Any = importlib.import_module("atlas.normalize.dates")
    _norm_parse_date: Any = getattr(_norm_mod, "parse_date", None)
except ImportError:
    _norm_parse_date = None


def parse_date_with_profile(
    text: Any,
    profile_format: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Parse date/datetime input with profile format and explicit timezone.

    Returns dict matching EventTime contract:
    {
        "original_text": str,
        "normalized_iso": str | None,
        "timezone": str | None,
        "ambiguity": TimeAmbiguity,
        "notes": str | None,
    }
    """
    if text is None:
        return {
            "original_text": "",
            "normalized_iso": None,
            "timezone": None,
            "ambiguity": TimeAmbiguity.UNPARSEABLE,
            "notes": "Null date input",
        }

    original_text = str(text).strip()
    if not original_text:
        return {
            "original_text": "",
            "normalized_iso": None,
            "timezone": None,
            "ambiguity": TimeAmbiguity.UNPARSEABLE,
            "notes": "Empty date input",
        }

    # Timezone determination: IST/Asia/Kolkata only when explicitly stated
    target_tz: str | None = None
    if timezone:
        tz_clean = timezone.strip().upper()
        if tz_clean in ("ASIA/KOLKATA", "IST", "+05:30", "+0530"):
            target_tz = "Asia/Kolkata"
        elif tz_clean in ("UTC", "Z", "+00:00", "+0000"):
            target_tz = "UTC"
        else:
            target_tz = timezone.strip()
    else:
        text_upper = original_text.upper()
        if "IST" in text_upper or "+05:30" in text_upper or "+0530" in text_upper:
            target_tz = "Asia/Kolkata"
        elif "UTC" in text_upper or text_upper.endswith("Z") or "+00:00" in text_upper:
            target_tz = "UTC"
        else:
            target_tz = None

    # Handle datetime/date objects directly
    if isinstance(text, datetime.datetime):
        iso_val = text.isoformat()
        return {
            "original_text": original_text,
            "normalized_iso": iso_val,
            "timezone": target_tz,
            "ambiguity": TimeAmbiguity.NONE,
            "notes": None,
        }
    if isinstance(text, datetime.date):
        dt = datetime.datetime.combine(text, datetime.time.min)
        return {
            "original_text": original_text,
            "normalized_iso": dt.isoformat(),
            "timezone": target_tz,
            "ambiguity": TimeAmbiguity.NONE,
            "notes": None,
        }

    # Handle Excel serial dates (int/float, or numeric string in valid serial range ~1000..100000)
    is_numeric_serial = False
    serial_val: float | None = None
    if isinstance(text, (int, float)):
        is_numeric_serial = True
        serial_val = float(text)
    elif re.match(r"^\d{4,6}(\.\d+)?$", original_text):
        val_candidate = float(original_text)
        if 1000 <= val_candidate <= 100000:
            is_numeric_serial = True
            serial_val = val_candidate

    if is_numeric_serial and serial_val is not None:
        try:
            excel_dt = from_excel(serial_val)
            if isinstance(excel_dt, datetime.date) and not isinstance(excel_dt, datetime.datetime):
                excel_dt = datetime.datetime.combine(excel_dt, datetime.time.min)
            return {
                "original_text": original_text,
                "normalized_iso": excel_dt.isoformat(),
                "timezone": target_tz,
                "ambiguity": TimeAmbiguity.NONE,
                "notes": "Parsed from Excel serial date",
            }
        except Exception:
            return {
                "original_text": original_text,
                "normalized_iso": None,
                "timezone": target_tz,
                "ambiguity": TimeAmbiguity.UNPARSEABLE,
                "notes": f"Invalid Excel serial number: {serial_val}",
            }

    # Profile format specified
    if profile_format:
        clean_format_text = re.sub(r"\s*(IST|\+05:30|\+0530|UTC|Z|\+00:00)\s*$", "", original_text, flags=re.I).strip()
        try:
            parsed = datetime.datetime.strptime(clean_format_text, profile_format)
            return {
                "original_text": original_text,
                "normalized_iso": parsed.isoformat(),
                "timezone": target_tz,
                "ambiguity": TimeAmbiguity.NONE,
                "notes": None,
            }
        except ValueError:
            # Try dateutil parse if strict profile format failed
            try:
                parsed_fallback = dateutil_parser.parse(clean_format_text)
                return {
                    "original_text": original_text,
                    "normalized_iso": parsed_fallback.isoformat(),
                    "timezone": target_tz,
                    "ambiguity": TimeAmbiguity.NONE,
                    "notes": f"Parsed using fallback parser (mismatched profile_format {profile_format})",
                }
            except Exception:
                return {
                    "original_text": original_text,
                    "normalized_iso": None,
                    "timezone": target_tz,
                    "ambiguity": TimeAmbiguity.UNPARSEABLE,
                    "notes": f"Failed to match profile format '{profile_format}'",
                }

    # No profile format provided: check DD/MM vs MM/DD ambiguity
    # Examples: 05/06/2023, 05-06-2023, 12/11/2021
    ambig_match = re.match(
        r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})(?:\s+(\d{1,2}:\d{1,2}(?::\d{1,2})?))?",
        original_text,
    )
    if ambig_match:
        p1 = int(ambig_match.group(1))
        p2 = int(ambig_match.group(2))
        year = int(ambig_match.group(3))
        time_part = ambig_match.group(4) or "00:00:00"

        if 1 <= p1 <= 12 and 1 <= p2 <= 12 and p1 != p2:
            return {
                "original_text": original_text,
                "normalized_iso": None,
                "timezone": target_tz,
                "ambiguity": TimeAmbiguity.DMY_MDY,
                "notes": "Ambiguous day/month ordering (both <= 12) without profile format",
            }
        if p1 > 12 and 1 <= p2 <= 12:
            # p1 is day, p2 is month (DMY)
            day, month = p1, p2
            if year < 100:
                year += 2000 if year < 70 else 1900
            try:
                dt_obj = datetime.datetime.fromisoformat(f"{year:04d}-{month:02d}-{day:02d}T{time_part}")
                return {
                    "original_text": original_text,
                    "normalized_iso": dt_obj.isoformat(),
                    "timezone": target_tz,
                    "ambiguity": TimeAmbiguity.NONE,
                    "notes": None,
                }
            except ValueError:
                pass
        elif 1 <= p1 <= 12 and p2 > 12:
            # p1 is month, p2 is day (MDY)
            month, day = p1, p2
            if year < 100:
                year += 2000 if year < 70 else 1900
            try:
                dt_obj = datetime.datetime.fromisoformat(f"{year:04d}-{month:02d}-{day:02d}T{time_part}")
                return {
                    "original_text": original_text,
                    "normalized_iso": dt_obj.isoformat(),
                    "timezone": target_tz,
                    "ambiguity": TimeAmbiguity.NONE,
                    "notes": None,
                }
            except ValueError:
                pass

    # Generic dateutil fallback
    try:
        clean_fallback = re.sub(r"\s*(IST|\+05:30|\+0530|UTC|Z|\+00:00)\s*$", "", original_text, flags=re.I).strip()
        parsed_dt = dateutil_parser.parse(clean_fallback)
        return {
            "original_text": original_text,
            "normalized_iso": parsed_dt.isoformat(),
            "timezone": target_tz,
            "ambiguity": TimeAmbiguity.NONE,
            "notes": None,
        }
    except Exception:
        return {
            "original_text": original_text,
            "normalized_iso": None,
            "timezone": target_tz,
            "ambiguity": TimeAmbiguity.UNPARSEABLE,
            "notes": "Unrecognized date format",
        }


__all__ = ["parse_date_with_profile"]
