"""
validate_data.py

Validates and summarizes investigation JSON datasets without assuming a rigid
final schema and without exposing unnecessary personal information (PII).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

# Traceability fields we want to preserve for source citations
CITATION_FIELDS: Tuple[str, ...] = (
    "record_id",
    "document_name",
    "page_number",
    "timestamp",
)

# Keywords in field names that may hold personal or sensitive narrative data.
# Note: "document_name" is explicitly excluded so source filenames remain visible.
SENSITIVE_KEY_SUBSTRINGS: Tuple[str, ...] = (
    "person",
    "witness",
    "suspect",
    "victim",
    "reported_by",
    "name",
    "phone",
    "email",
    "address",
    "ssn",
    "dob",
    "birth",
    "contact",
    "description",
    "narrative",
    "statement",
    "location",
    "notes",
)

SAFE_FIELD_ALLOWLIST: Set[str] = {
    "case_id",
    "record_id",
    "record_type",
    "document_name",
    "page_number",
    "timestamp",
    "status",
    "amount_usd",
    "is_fictional_mock",
    "schema_status",
    "generated_at",
    "event_id",
    "event_type",
    "transaction_id",
    "mention_id",
    "entity_id",
    "entity_type",
    "file_name",
    "source_id",
    "_source_id",
    "schema_version",
    "payload_type",
}

KNOWN_TOP_LEVEL_METADATA_KEYS: Set[str] = {
    "schema_version",
    "payload_type",
    "case",
    "case_id",
    "case_info",
    "source_index",
    "processing",
    "_disclaimer",
    "is_fictional_mock",
    "schema_status",
    "generated_at",
    "metadata",
}



def is_sensitive_field(field_name: str) -> bool:
    """Return True if a JSON key might contain personal or sensitive details."""
    normalized = field_name.strip().lower()
    if normalized in SAFE_FIELD_ALLOWLIST:
        return False
    return any(token in normalized for token in SENSITIVE_KEY_SUBSTRINGS)


def sanitize_record_structure(record: Dict[str, Any]) -> Dict[str, str]:
    """
    Inspect a record dictionary and return only its field names and data types,
    explicitly marking sensitive/PII fields as redacted without exposing values.
    """
    sanitized: Dict[str, str] = {}
    for key, value in record.items():
        type_name = "null" if value is None else type(value).__name__
        if is_sensitive_field(key):
            sanitized[key] = f"{type_name} [REDACTED_PII]"
        else:
            sanitized[key] = type_name
    return sanitized


def _map_nested_record(
    raw_dict: Dict[str, Any],
    parent_case_id: Optional[str] = None,
    default_record_type: str = "unspecified",
    source_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Map heterogeneous record fields into a common internal representation
    while preserving 100% of original fields, provenance, and data types.
    """
    rec = dict(raw_dict)
    sources = source_map or {}

    # Case ID: use record's own case_id if present, else inherit parent case_id
    rec_cid = rec.get("case_id")
    if rec_cid and str(rec_cid).strip():
        rec["case_id"] = str(rec_cid).strip()
    elif parent_case_id:
        rec["case_id"] = str(parent_case_id).strip()

    # Record ID: map from available identifier candidates without fabricating values
    if not rec.get("record_id"):
        for id_key in (
            "record_id",
            "Record ID",
            "event_id",
            "transaction_id",
            "txn_id",
            "mention_id",
            "entity_id",
            "cctv_id",
            "anpr_id",
            "osint_id",
            "id",
        ):
            val = rec.get(id_key)
            if val is not None and str(val).strip():
                rec["record_id"] = str(val).strip()
                break

    # Record Type: preserve or assign category
    if not rec.get("record_type") or not str(rec.get("record_type")).strip():
        if rec.get("event_type"):
            rec["record_type"] = str(rec["event_type"]).strip()
        elif default_record_type:
            rec["record_type"] = str(default_record_type).strip()
        else:
            rec["record_type"] = "unspecified"
    else:
        rec["record_type"] = str(rec["record_type"]).strip()

    # Document Name & Source Provenance: map from source_index if not already explicit
    if not rec.get("document_name") and not rec.get("file_name"):
        sid = (
            rec.get("_source_id")
            or rec.get("source_id")
            or rec.get("source_ref")
            or rec.get("source")
        )
        if isinstance(sid, str) and sid in sources:
            source_obj = sources[sid]
            rec["document_name"] = source_obj.get("file_name") or source_obj.get("document_name")
        elif isinstance(rec.get("source_refs"), (list, tuple)):
            # Handle multi-source references (e.g. in resolved_entities)
            matched_names = [
                sources[s].get("file_name")
                for s in rec["source_refs"]
                if isinstance(s, str) and s in sources and sources[s].get("file_name")
            ]
            if matched_names:
                rec["document_name"] = ", ".join(matched_names)
    elif rec.get("file_name") and not rec.get("document_name"):
        rec["document_name"] = str(rec["file_name"]).strip()

    # Page Number: preserve if available, do not fabricate
    if rec.get("page_number") is not None:
        pass
    elif rec.get("page") is not None:
        rec["page_number"] = rec["page"]
    else:
        rec["page_number"] = None

    # Timestamp: normalize candidate timestamp fields
    if not rec.get("timestamp"):
        if rec.get("booking_time_ist"):
            rec["timestamp"] = str(rec["booking_time_ist"]).strip()
        elif rec.get("Call date") and rec.get("Call Initiation Time (CIT)"):
            rec["timestamp"] = f"{str(rec['Call date']).strip()} {str(rec['Call Initiation Time (CIT)']).strip()}"
        elif rec.get("datetime"):
            rec["timestamp"] = str(rec["datetime"]).strip()
        elif rec.get("event_time"):
            rec["timestamp"] = str(rec["event_time"]).strip()
        elif rec.get("date"):
            rec["timestamp"] = str(rec["date"]).strip()
        else:
            rec["timestamp"] = None

    if "document_name" not in rec:
        rec["document_name"] = None
    if "amount_usd" not in rec:
        rec["amount_usd"] = None

    # Description / Summary fallback for UI display
    if not rec.get("description") and not rec.get("summary"):
        if rec.get("narration"):
            rec["description"] = rec["narration"]
        elif rec.get("raw_value"):
            etype = rec.get("entity_type", "entity")
            rec["description"] = f"{etype}: {rec['raw_value']}"
        elif rec.get("canonical_value"):
            etype = rec.get("entity_type", "entity")
            rec["description"] = f"Resolved {etype}: {rec['canonical_value']}"

    return rec


def _extract_cases_and_records(
    data: Any,
) -> Tuple[List[str], List[Dict[str, Any]], List[str], List[str]]:
    """
    Extract case IDs and individual records from a flexible JSON structure.
    Supports:
      1. A dict with a 'cases' list (each case containing a 'records' list)
      2. A dict with a flat 'records' or 'items' list
      3. A top-level list of record dicts
      4. Nested case files containing 'case', 'source_index', 'events',
         'structured_records' (with heterogeneous groups), 'entity_mentions',
         and 'resolved_entities'.
    Returns:
      (discovered_case_ids, extracted_records, errors, warnings)
    """
    discovered_case_ids: List[str] = []
    extracted_records: List[Dict[str, Any]] = []
    errors: List[str] = []
    warnings: List[str] = []

    if isinstance(data, dict):
        # 1. Legacy Hierarchical Schema: { "cases": [ { "case_id": "...", "records": [...] } ] }
        if "cases" in data and isinstance(data["cases"], list):
            for idx, case_obj in enumerate(data["cases"]):
                if not isinstance(case_obj, dict):
                    errors.append(f"Case entry at index {idx} is not a JSON object.")
                    continue

                parent_case_id = case_obj.get("case_id")
                if not parent_case_id or not isinstance(parent_case_id, str):
                    errors.append(f"Case entry at index {idx} is missing a valid 'case_id'.")
                else:
                    if parent_case_id not in discovered_case_ids:
                        discovered_case_ids.append(parent_case_id)

                records_list = case_obj.get("records", [])
                if not isinstance(records_list, list):
                    errors.append(
                        f"Case '{parent_case_id or idx}' has a non-list 'records' field."
                    )
                    continue

                for rec_idx, rec in enumerate(records_list):
                    if not isinstance(rec, dict):
                        errors.append(
                            f"Record at index {rec_idx} in case '{parent_case_id}' is not a dict."
                        )
                        continue

                    rec_copy = dict(rec)
                    rec_case_id = rec_copy.get("case_id")
                    if rec_case_id and parent_case_id and rec_case_id != parent_case_id:
                        errors.append(
                            f"Cross-case mismatch: record '{rec_copy.get('record_id', rec_idx)}' "
                            f"has case_id '{rec_case_id}' inside parent case '{parent_case_id}'."
                        )
                    elif not rec_case_id and parent_case_id:
                        rec_copy["case_id"] = parent_case_id
                        warnings.append(
                            f"Record '{rec_copy.get('record_id', rec_idx)}' inherited "
                            f"case_id '{parent_case_id}' from parent case object."
                        )
                    extracted_records.append(rec_copy)

        # 2. Legacy Flat Records Schema: { "records": [...] } or { "items": [...] }
        elif "records" in data and isinstance(data["records"], list):
            for idx, rec in enumerate(data["records"]):
                if not isinstance(rec, dict):
                    errors.append(f"Record at index {idx} is not a JSON object.")
                    continue
                extracted_records.append(dict(rec))
                cid = rec.get("case_id")
                if isinstance(cid, str) and cid and cid not in discovered_case_ids:
                    discovered_case_ids.append(cid)

        elif "items" in data and isinstance(data["items"], list):
            for idx, rec in enumerate(data["items"]):
                if not isinstance(rec, dict):
                    errors.append(f"Record at index {idx} is not a JSON object.")
                    continue
                extracted_records.append(dict(rec))
                cid = rec.get("case_id")
                if isinstance(cid, str) and cid and cid not in discovered_case_ids:
                    discovered_case_ids.append(cid)

        # 3. Nested Case Structure (e.g. ATLAS, Member 3 output, or multi-collection)
        else:
            # Discover case identifier from case metadata or top-level field
            parent_case_id: Optional[str] = None
            if isinstance(data.get("case"), dict):
                cid_val = data["case"].get("case_id")
                if cid_val and str(cid_val).strip():
                    parent_case_id = str(cid_val).strip()
            elif isinstance(data.get("case"), str) and data.get("case").strip():
                parent_case_id = data["case"].strip()
            elif isinstance(data.get("case_id"), str) and data.get("case_id").strip():
                parent_case_id = data.get("case_id").strip()

            if parent_case_id and parent_case_id not in discovered_case_ids:
                discovered_case_ids.append(parent_case_id)

            # Build source index lookup map for provenance tracking
            source_map: Dict[str, Dict[str, Any]] = {}
            if "source_index" in data and isinstance(data["source_index"], list):
                for s_idx, s_obj in enumerate(data["source_index"]):
                    if isinstance(s_obj, dict):
                        sid = s_obj.get("source_id") or s_obj.get("id")
                        if sid:
                            source_map[str(sid).strip()] = s_obj
                    else:
                        warnings.append(
                            f"Source index item at index {s_idx} is not a JSON object; skipped."
                        )
            elif "source_index" in data and not isinstance(data["source_index"], list):
                warnings.append(
                    "Top-level 'source_index' is present but is not a list; provenance lookup may be limited."
                )

            # (A) Events
            if "events" in data:
                if isinstance(data["events"], list):
                    for idx, ev in enumerate(data["events"]):
                        if isinstance(ev, dict):
                            extracted_records.append(
                                _map_nested_record(
                                    ev,
                                    parent_case_id=parent_case_id,
                                    default_record_type="event",
                                    source_map=source_map,
                                )
                            )
                        else:
                            warnings.append(f"Event entry at index {idx} is not a JSON object; skipped.")
                else:
                    warnings.append("Top-level 'events' field is present but is not a list.")

            # (B) Structured records (heterogeneous groups discovered dynamically)
            if "structured_records" in data:
                sr = data["structured_records"]
                if isinstance(sr, dict):
                    for group_name, group_items in sr.items():
                        if isinstance(group_items, list):
                            for idx, item in enumerate(group_items):
                                if isinstance(item, dict):
                                    extracted_records.append(
                                        _map_nested_record(
                                            item,
                                            parent_case_id=parent_case_id,
                                            default_record_type=group_name,
                                            source_map=source_map,
                                        )
                                    )
                                else:
                                    warnings.append(
                                        f"Record at index {idx} in structured_records['{group_name}'] "
                                        "is not a JSON object; skipped."
                                    )
                        else:
                            warnings.append(
                                f"Structured records group '{group_name}' is not a list "
                                f"(found {type(group_items).__name__}); skipped."
                            )
                else:
                    warnings.append(
                        "Top-level 'structured_records' is present but is not a JSON object."
                    )

            # (C) Entity mentions
            if "entity_mentions" in data:
                if isinstance(data["entity_mentions"], list):
                    for idx, ment in enumerate(data["entity_mentions"]):
                        if isinstance(ment, dict):
                            etype = ment.get("entity_type", "unspecified")
                            extracted_records.append(
                                _map_nested_record(
                                    ment,
                                    parent_case_id=parent_case_id,
                                    default_record_type=f"entity_mention_{etype}",
                                    source_map=source_map,
                                )
                            )
                        else:
                            warnings.append(
                                f"Entity mention at index {idx} is not a JSON object; skipped."
                            )
                else:
                    warnings.append("Top-level 'entity_mentions' is present but is not a list.")

            # (D) Resolved entities
            if "resolved_entities" in data:
                if isinstance(data["resolved_entities"], list):
                    for idx, ent in enumerate(data["resolved_entities"]):
                        if isinstance(ent, dict):
                            etype = ent.get("entity_type", "unspecified")
                            extracted_records.append(
                                _map_nested_record(
                                    ent,
                                    parent_case_id=parent_case_id,
                                    default_record_type=f"resolved_entity_{etype}",
                                    source_map=source_map,
                                )
                            )
                        else:
                            warnings.append(
                                f"Resolved entity at index {idx} is not a JSON object; skipped."
                            )
                else:
                    warnings.append("Top-level 'resolved_entities' is present but is not a list.")

            # (E) Dynamically discover any other custom record collections
            for key, val in data.items():
                if key in KNOWN_TOP_LEVEL_METADATA_KEYS or key in (
                    "events",
                    "structured_records",
                    "entity_mentions",
                    "resolved_entities",
                    "cases",
                    "records",
                    "items",
                ):
                    continue
                if isinstance(val, list):
                    dict_count = sum(1 for item in val if isinstance(item, dict))
                    if dict_count > 0:
                        for idx, item in enumerate(val):
                            if isinstance(item, dict):
                                extracted_records.append(
                                    _map_nested_record(
                                        item,
                                        parent_case_id=parent_case_id,
                                        default_record_type=key,
                                        source_map=source_map,
                                    )
                                )
                            else:
                                warnings.append(
                                    f"Record at index {idx} in '{key}' is not a JSON object; skipped."
                                )
                    else:
                        warnings.append(
                            f"Top-level list '{key}' does not contain dictionary records; skipped."
                        )
                elif isinstance(val, dict):
                    warnings.append(
                        f"Unrecognized top-level object '{key}' could not be safely mapped to evidence records."
                    )

            # Extract any remaining case IDs from the extracted records
            for rec in extracted_records:
                cid = rec.get("case_id")
                if cid and isinstance(cid, str) and cid.strip() and cid.strip() not in discovered_case_ids:
                    discovered_case_ids.append(cid.strip())

            if not extracted_records:
                warnings.append(
                    "Top-level JSON object does not contain recognizable case records or evidence collections."
                )

    elif isinstance(data, list):
        for idx, rec in enumerate(data):
            if not isinstance(rec, dict):
                errors.append(f"Top-level list item at index {idx} is not a JSON object.")
                continue
            extracted_records.append(dict(rec))
            cid = rec.get("case_id")
            if isinstance(cid, str) and cid and cid not in discovered_case_ids:
                discovered_case_ids.append(cid)
    else:
        errors.append("Top-level JSON value must be an object (dict) or array (list).")

    return discovered_case_ids, extracted_records, errors, warnings


def validate_and_summarize(data: Any) -> Dict[str, Any]:
    """
    Validate the parsed JSON data and return a privacy-safe structural summary
    with exact Python-computed counts.
    """
    case_ids, records, errors, warnings = _extract_cases_and_records(data)

    top_level_type = type(data).__name__
    top_level_keys = list(data.keys()) if isinstance(data, dict) else []
    is_fictional_mock = (
        bool(data.get("is_fictional_mock"))
        or (isinstance(data.get("processing"), dict) and bool(data["processing"].get("mock_backend")))
    ) if isinstance(data, dict) else False


    records_per_case: Counter[str] = Counter()
    record_types_counter: Counter[str] = Counter()
    citation_field_counts: Dict[str, int] = {field: 0 for field in CITATION_FIELDS}
    missing_by_case_field: Dict[Tuple[str, str], List[str]] = {}
    decimal_totals_by_case: Dict[str, Decimal] = {cid: Decimal("0.00") for cid in case_ids}

    seen_record_ids: Set[str] = set()
    discovered_field_schema: Dict[str, str] = {}
    redacted_pii_fields: Set[str] = set()

    for idx, rec in enumerate(records):
        # Inspect field schema without storing raw values
        sanitized = sanitize_record_structure(rec)
        for field_name, type_label in sanitized.items():
            if field_name not in discovered_field_schema or discovered_field_schema[field_name].startswith("null"):
                discovered_field_schema[field_name] = type_label
            if "[REDACTED_PII]" in type_label:
                redacted_pii_fields.add(field_name)

        # Validate record_id
        rec_id = rec.get("record_id")
        if not rec_id or not isinstance(rec_id, str):
            errors.append(f"Record at position {idx} is missing a valid string 'record_id'.")
            rec_label = f"<missing_id_{idx}>"
        else:
            rec_label = rec_id
            if rec_id in seen_record_ids:
                errors.append(f"Duplicate 'record_id' detected: '{rec_id}'.")
            seen_record_ids.add(rec_id)

        # Validate case_id
        cid = rec.get("case_id")
        if not cid or not isinstance(cid, str):
            errors.append(f"Record '{rec_label}' is missing a valid 'case_id'.")
        else:
            if cid not in case_ids:
                case_ids.append(cid)
            records_per_case[cid] += 1

            # Calculate exact numeric totals per case using Decimal arithmetic
            amt = rec.get("amount_usd")
            if amt is not None and not isinstance(amt, bool):
                try:
                    dec_val = Decimal(str(amt))
                    if cid not in decimal_totals_by_case:
                        decimal_totals_by_case[cid] = Decimal("0.00")
                    decimal_totals_by_case[cid] += dec_val
                except (InvalidOperation, TypeError):
                    pass

        # Count record_type
        rtype = rec.get("record_type")
        if isinstance(rtype, str) and rtype.strip():
            record_types_counter[rtype.strip()] += 1
        else:
            record_types_counter["unspecified"] += 1

        # Check citation field availability
        for cfield in CITATION_FIELDS:
            val = rec.get(cfield)
            if val is not None and val != "":
                citation_field_counts[cfield] += 1
            else:
                if cfield != "record_id":  # missing record_id is already logged as an error
                    missing_by_case_field.setdefault((cid or "UNKNOWN", cfield), []).append(rec_label)

    # Grouped warnings per case and citation field to avoid spamming the UI with hundreds of identical messages
    for (cid_key, cfield), missing_ids in sorted(missing_by_case_field.items()):
        cnt = len(missing_ids)
        if cnt <= 3:
            id_list_str = ", ".join(missing_ids)
            warnings.append(
                f"Record(s) {id_list_str} in case '{cid_key}' are missing citation field '{cfield}'."
            )
        else:
            sample_ids_str = ", ".join(missing_ids[:2])
            if cfield == "page_number":
                warnings.append(
                    f"Case '{cid_key}': {cnt} records (including {sample_ids_str}) do not have a recorded 'page_number' "
                    "(page numbers are not applicable to digital structured records such as CDR or financial logs)."
                )
            elif cfield == "timestamp":
                warnings.append(
                    f"Case '{cid_key}': {cnt} records (including {sample_ids_str}) do not have a recorded 'timestamp'."
                )
            else:
                warnings.append(
                    f"Case '{cid_key}': {cnt} records (including {sample_ids_str}) are missing citation field '{cfield}'."
                )

    is_valid = len(errors) == 0

    return {
        "is_valid": is_valid,
        "is_fictional_mock": is_fictional_mock,
        "top_level_type": top_level_type,
        "top_level_keys": top_level_keys,
        "total_cases": len(case_ids),
        "case_ids": case_ids,
        "total_records": len(records),
        "records_per_case": dict(records_per_case),
        "record_types_breakdown": dict(record_types_counter),
        "amount_totals_by_case": {cid: float(round(tot, 2)) for cid, tot in decimal_totals_by_case.items()},
        "citation_field_coverage": citation_field_counts,
        "discovered_record_fields": discovered_field_schema,
        "redacted_sensitive_fields": sorted(redacted_pii_fields),
        "errors": errors,
        "warnings": warnings,
    }


def load_and_validate_file(filepath: str | Path) -> Dict[str, Any]:
    """Load a JSON file from disk and return its validation and summary dictionary."""
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        return {
            "is_valid": False,
            "is_fictional_mock": False,
            "top_level_type": "none",
            "top_level_keys": [],
            "total_cases": 0,
            "case_ids": [],
            "total_records": 0,
            "records_per_case": {},
            "record_types_breakdown": {},
            "amount_totals_by_case": {},
            "citation_field_coverage": {field: 0 for field in CITATION_FIELDS},
            "discovered_record_fields": {},
            "redacted_sensitive_fields": [],
            "errors": [f"File not found: {path}"],
            "warnings": [],
        }

    try:
        raw_text = path.read_text(encoding="utf-8")
        parsed_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "is_valid": False,
            "is_fictional_mock": False,
            "top_level_type": "invalid_json",
            "top_level_keys": [],
            "total_cases": 0,
            "case_ids": [],
            "total_records": 0,
            "records_per_case": {},
            "record_types_breakdown": {},
            "amount_totals_by_case": {},
            "citation_field_coverage": {field: 0 for field in CITATION_FIELDS},
            "discovered_record_fields": {},
            "redacted_sensitive_fields": [],
            "errors": [f"Invalid JSON syntax in '{path.name}': {exc.msg} (line {exc.lineno})"],
            "warnings": [],
        }

    return validate_and_summarize(parsed_data)


def format_summary_report(summary: Dict[str, Any]) -> str:
    """
    Format the validation summary into a clean, human-readable text report.
    Contains only structural metadata, IDs, and exact counts (no PII values).
    """
    status_str = "PASSED" if summary["is_valid"] else "FAILED"
    mock_str = "YES (Fictional Mock Data)" if summary["is_fictional_mock"] else "NO / Unspecified"

    lines = [
        "============================================================",
        " INVESTIGATION DATASET VALIDATION & PRIVACY-SAFE SUMMARY",
        "============================================================",
        f"Validation Status   : {status_str}",
        f"Fictional Mock Flag : {mock_str}",
        f"Top-Level JSON Type : {summary['top_level_type']}",
        f"Top-Level Keys      : {', '.join(summary['top_level_keys']) or 'None'}",
        "------------------------------------------------------------",
        "EXACT COUNTS (Computed by Python)",
        f"  Total Cases       : {summary['total_cases']}",
        f"  Total Records     : {summary['total_records']}",
    ]

    if summary["records_per_case"]:
        lines.append("  Records per Case  :")
        for cid, count in summary["records_per_case"].items():
            case_total = summary["amount_totals_by_case"].get(cid, 0.0)
            lines.append(
                f"    - {cid}: {count} record(s) | Recorded USD Total: ${case_total:,.2f}"
            )

    if summary["record_types_breakdown"]:
        lines.append("  Record Types      :")
        for rtype, count in summary["record_types_breakdown"].items():
            lines.append(f"    - {rtype}: {count}")

    total_recs = summary["total_records"]
    lines.append("------------------------------------------------------------")
    lines.append("SOURCE CITATION FIELD COVERAGE")
    for cfield, count in summary["citation_field_coverage"].items():
        lines.append(f"  - {cfield:<15}: {count}/{total_recs} record(s)")

    lines.append("------------------------------------------------------------")
    lines.append("DISCOVERED RECORD SCHEMA (PII Values Suppressed)")
    for fname, ftype in summary["discovered_record_fields"].items():
        lines.append(f"  - {fname:<18}: {ftype}")

    if summary["warnings"]:
        lines.append("------------------------------------------------------------")
        lines.append(f"WARNINGS ({len(summary['warnings'])})")
        for warning in summary["warnings"]:
            lines.append(f"  [!] {warning}")

    if summary["errors"]:
        lines.append("------------------------------------------------------------")
        lines.append(f"VALIDATION ERRORS ({len(summary['errors'])})")
        for err in summary["errors"]:
            lines.append(f"  [X] {err}")

    lines.append("============================================================")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    """CLI entry point for validating and summarizing an investigation JSON file."""
    args = argv if argv is not None else sys.argv[1:]
    default_path = Path("data/mock_investigation_data.json")
    target_path = Path(args[0]) if args else default_path

    summary = load_and_validate_file(target_path)
    print(format_summary_report(summary))
    return 0 if summary["is_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
