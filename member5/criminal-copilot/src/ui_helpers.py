"""
ui_helpers.py

Helper utilities for the Streamlit UI in AI-Powered Criminal Investigation Copilot.
Separates pure data formatting, case listing, and filtering logic from rendering
so they can be unit-tested deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.evidence_search import (
    calculate_case_metrics,
    filter_by_record_type,
    format_evidence_citation,
    get_citation_metadata,
    load_and_normalize_records,
    search_by_case_id,
    search_text,
    sort_records_chronologically,
)
from src.validate_data import validate_and_summarize


def get_available_cases(records: List[Dict[str, Any]]) -> List[str]:
    """Return a sorted list of unique case IDs discovered in records."""
    unique_cases = {
        str(r.get("case_id")).strip()
        for r in records
        if r.get("case_id") and str(r.get("case_id")).strip()
    }
    return sorted(unique_cases)


def get_record_types_for_case(records: List[Dict[str, Any]], case_id: str) -> List[str]:
    """Return distinct record types available within a specific case."""
    case_recs = search_by_case_id(records, case_id)
    types = {
        str(r.get("record_type", "unspecified")).strip()
        for r in case_recs
        if r.get("record_type")
    }
    return ["All Types"] + sorted(types)


def filter_case_evidence(
    records: List[Dict[str, Any]],
    case_id: str,
    query: str = "",
    selected_type: str = "All Types",
) -> List[Dict[str, Any]]:
    """
    Apply case-isolation, optional text query, and optional record-type filter.
    Guarantees no records from any other case are returned.
    """
    if not case_id or not case_id.strip():
        return []

    # 1. Enforce strict case isolation first
    scoped_records = search_by_case_id(records, case_id.strip())

    # 2. Filter by record type if requested
    if selected_type and selected_type != "All Types":
        scoped_records = filter_by_record_type(
            scoped_records, record_type=selected_type, case_id=case_id.strip()
        )

    # 3. Filter by search text if provided
    if query and query.strip():
        scoped_records = search_text(
            scoped_records, query=query.strip(), case_id=case_id.strip()
        )

    return scoped_records


def format_citation_card(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format evidence record coordinates into clear UI-friendly labels,
    explicitly marking missing metadata as [NOT RECORDED] rather than inventing values.
    """
    citation = get_citation_metadata(record)
    doc_name = citation.get("document_name") or "[NOT RECORDED]"
    page_num = citation.get("page_number")
    page_display = str(page_num) if page_num is not None else "[NOT RECORDED]"
    time_val = citation.get("timestamp") or "[NOT RECORDED]"
    rec_id = citation.get("record_id") or "[NOT RECORDED]"
    case_id = citation.get("case_id") or "[NOT RECORDED]"
    rtype = record.get("record_type") or "unspecified"
    amt = record.get("amount_usd")

    return {
        "record_id": rec_id,
        "case_id": case_id,
        "document_name": doc_name,
        "page_number": page_display,
        "timestamp": time_val,
        "record_type": rtype,
        "amount_usd": f"${amt:,.2f}" if amt is not None else None,
        "has_complete_citations": citation.get("has_complete_citations", False),
        "citation_string": format_evidence_citation(record),
    }


def extract_metadata_from_dict(data: Any) -> Dict[str, Any]:
    """Extract top-level metadata from a parsed JSON dictionary or list."""
    if isinstance(data, dict):
        is_mock = bool(
            data.get("is_fictional_mock")
            or (isinstance(data.get("processing"), dict) and data["processing"].get("mock_backend"))
            or (isinstance(data.get("case"), dict) and "SYN-" in str(data["case"].get("fir_number", "")))
        )
        disclaimer = data.get("_disclaimer")
        if not disclaimer and is_mock:
            disclaimer = (
                "SYNTHETIC / MOCK CASE DATASET: All events, entities, and records in this "
                "payload are simulated for research, education, and investigation testing."
            )
        case_info = data.get("case") if isinstance(data.get("case"), dict) else None
        return {
            "is_fictional_mock": is_mock,
            "disclaimer": disclaimer,
            "schema_status": data.get("schema_status") or data.get("payload_type"),
            "generated_at": data.get("generated_at"),
            "schema_version": data.get("schema_version"),
            "case_info": case_info,
        }
    return {
        "is_fictional_mock": False,
        "disclaimer": None,
        "schema_status": None,
        "generated_at": None,
        "schema_version": None,
        "case_info": None,
    }


def load_dataset_metadata(filepath: Union[str, Path]) -> Dict[str, Any]:
    """Load top-level metadata from the JSON file to check for mock dataset flags."""
    path = Path(filepath)
    if not path.exists():
        return {"is_fictional_mock": False, "disclaimer": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return extract_metadata_from_dict(data)
    except Exception:
        pass
    return {"is_fictional_mock": False, "disclaimer": None}


def parse_uploaded_json(
    raw_payload: Union[bytes, str]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str], List[str]]:
    """
    Parse an uploaded JSON byte payload or string, validate its structure,
    and return normalized records, metadata, validation errors, and warnings.
    Returns: (records, metadata, errors, warnings)
    """
    if isinstance(raw_payload, bytes):
        try:
            text = raw_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            return [], {}, [f"Encoding error: file must be UTF-8 encoded ({exc})"], []
    else:
        text = str(raw_payload)

    text_stripped = text.strip()
    if not text_stripped:
        return [], {}, ["Uploaded file is empty."], []

    try:
        parsed_data = json.loads(text_stripped)
    except json.JSONDecodeError as exc:
        return [], {}, [f"Invalid JSON syntax: {exc.msg} (line {exc.lineno}, column {exc.colno})"], []

    summary = validate_and_summarize(parsed_data)
    errors = summary.get("errors", [])
    warnings = summary.get("warnings", [])

    try:
        records = load_and_normalize_records(parsed_data)
    except Exception as exc:
        errors.append(f"Normalization failed: {exc}")
        records = []

    metadata = extract_metadata_from_dict(parsed_data)
    return records, metadata, errors, warnings
