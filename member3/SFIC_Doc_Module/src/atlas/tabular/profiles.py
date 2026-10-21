"""Profile loader and schema detector for tabular evidence.

Implements PLAN.md section 5.7:
- load_profile(path: Path) -> dict: Reads YAML profile definitions.
- detect_profile(headers: list[str], profiles_dir: Path) -> str | None:
  Performs normalized header set comparison against registered profiles.
  Unknown headers or missing required headers return None and trigger mapping_unconfirmed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from atlas.contracts.enums import ReviewItemStatus, ReviewKind
from atlas.contracts.ids import make_review_id
from atlas.contracts.records import ReviewItem

# Known valid fields per profile family
PROFILE_KNOWN_FIELDS: dict[str, set[str]] = {
    "cdr": {
        "a_party",
        "b_party",
        "start_time",
        "duration_s",
        "call_type",
        "imei",
        "cell_id",
        "target_a_party_number",
        "b_party_number",
        "call_type_in_out",
        "type_of_connection_prepaid_postpaid",
        "lrn_a_b_party_number",
        "translation_of_lrn",
        "call_date",
        "call_initiation_time_cit",
        "call_duration_second",
        "first_bts_location",
        "first_cell_global_id_mcc_mnc_lac_site_id",
        "last_bts_location",
        "last_cell_global_id",
        "sms_centre_no",
        "service_type",
        "imei_esn",
        "imsi_min",
        "call_forwarding_number",
        "roaming_network_circle",
        "switch_id_msc_id",
        "in_tg",
        "out_tg",
        "record_id",
        "call_time",
    },
    "bank": {
        "txn_id",
        "txn_date",
        "from_account",
        "to_account",
        "amount",
        "currency",
        "narration",
        "balance",
        "transaction_id",
        "account_number",
        "booking_time_ist",
        "value_date",
        "channel",
        "reference_number",
        "counterparty_name_recorded",
        "counterparty_name",
        "counterparty_account",
        "debit_inr",
        "credit_inr",
        "balance_inr",
        "status",
        "related_reference",
        "debit",
        "credit",
    },
    "anpr": {
        "event_id",
        "camera_id",
        "source_clock_ist",
        "clock_offset_seconds",
        "reviewed_time_ist",
        "site",
        "plate_ocr",
        "plate_reviewed",
        "ocr_confidence",
        "direction",
        "lane",
        "clip_reference",
        "visibility",
        "review_note",
        "timestamp",
        "source_time",
        "clock_offset",
    },
    "tower": {
        "observation_id",
        "target_number",
        "event_time_ist",
        "cell_global_id",
        "site_description",
        "site_latitude",
        "site_longitude",
        "sector_azimuth_deg",
        "technology",
        "location_basis",
        "accuracy_note",
        "timestamp",
        "site",
        "latitude",
        "longitude",
        "azimuth",
    },
}


def normalize_header(header: str) -> str:
    """Normalize a header string: lowercase, strip, convert spaces/hyphens to underscores."""
    cleaned = header.strip().lower()
    cleaned = re.sub(r"[\s\-\/\.]+", "_", cleaned)
    cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)
    return cleaned.strip("_")


def load_profile(path: Path | str) -> dict[str, Any]:
    """Load and validate a YAML profile definition."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Profile file not found: {file_path}")

    with open(file_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Profile {file_path} must be a YAML dictionary")

    # Ensure required configuration keys
    if "name" not in data or "required_headers" not in data:
        raise ValueError(f"Profile {file_path} missing required 'name' or 'required_headers'")

    return data


def detect_profile(headers: list[str], profiles_dir: Path | str) -> str | None:
    """Detect matching profile for a list of table headers using normalized set comparison.

    Returns the profile name if exact required headers match and no unknown headers exist,
    or None if headers cannot be confirmed.
    """
    p_dir = Path(profiles_dir)
    if not p_dir.exists() or not p_dir.is_dir():
        return None

    norm_headers = [normalize_header(h) for h in headers if h.strip()]
    if not norm_headers:
        return None

    # Search through YAML profiles in profiles_dir
    candidate_files = sorted(p_dir.glob("*.yaml"))
    for p_file in candidate_files:
        try:
            profile = load_profile(p_file)
        except Exception:
            continue

        p_name = profile.get("name", "")
        req_headers = set(profile.get("required_headers", []))
        aliases = profile.get("header_aliases", {})
        id_cols = set(profile.get("id_columns", []))

        # Determine family known fields
        p_lower = str(p_name).lower()
        if "cdr" in p_lower:
            family = "cdr"
        elif "bank" in p_lower:
            family = "bank"
        elif "anpr" in p_lower:
            family = "anpr"
        elif "tower" in p_lower:
            family = "tower"
        else:
            family = ""
        family_fields = PROFILE_KNOWN_FIELDS.get(family, set())

        known_headers = req_headers | id_cols | family_fields | set(aliases.keys()) | set(aliases.values())

        # Map input headers to canonical names
        mapped_headers: set[str] = set()
        has_unknown = False

        for nh in norm_headers:
            canonical = aliases.get(nh, nh)
            if canonical not in known_headers and nh not in known_headers:
                has_unknown = True
                break
            mapped_headers.add(canonical)

        if has_unknown:
            continue

        # Check that all required headers are present
        if req_headers.issubset(mapped_headers):
            return str(p_name) if p_name else None

    return None


def create_mapping_unconfirmed_review(
    case_id: str,
    doc_id: str,
    headers: list[str],
    detail: str = "",
) -> ReviewItem:
    """Generate a ReviewItem for unconfirmed table headers."""
    headers_str = ", ".join(headers)
    msg = detail or f"Headers {headers_str} could not be confirmed against any active profile."
    rev_id = make_review_id(case_id, ReviewKind.MAPPING_UNCONFIRMED.value, doc_id, msg)

    return ReviewItem(
        review_id=rev_id,
        case_id=case_id,
        kind=ReviewKind.MAPPING_UNCONFIRMED,
        target_ids=[doc_id],
        detail=msg,
        status=ReviewItemStatus.OPEN,
    )


__all__ = [
    "create_mapping_unconfirmed_review",
    "detect_profile",
    "load_profile",
    "normalize_header",
]
