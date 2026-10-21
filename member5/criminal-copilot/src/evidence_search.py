"""
evidence_search.py

Python Evidence Retrieval Engine for AI-Powered Criminal Investigation Copilot.
Provides schema-flexible, case-isolated searching, filtering, exact numerical
aggregation, chronological ordering, and source citation preservation.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.validate_data import (
    CITATION_FIELDS,
    _extract_cases_and_records,
    is_sensitive_field,
)

CORE_CITATION_KEYS: Tuple[str, ...] = (
    "record_id",
    "case_id",
    "document_name",
    "page_number",
    "timestamp",
)


TIMESTAMP_FORMATS: Tuple[str, ...] = (
    "%d-%m-%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y/%m/%d %H:%M:%S",
)


def parse_iso_timestamp(timestamp_val: Any) -> Optional[datetime]:
    """
    Safely parse an ISO-8601 or common structured timestamp string into a datetime object.
    Supports UTC 'Z' suffixes, offset notations, and date/time formats across Python 3.9+.
    Returns None if timestamp_val is missing, empty, or unparseable.
    """
    if not isinstance(timestamp_val, str) or not timestamp_val.strip():
        return None
    cleaned = timestamp_val.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        # Ensure UTC timezone awareness if tzinfo is absent
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass

    for fmt in TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None



def get_citation_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspect a record and return explicit source citation metadata.
    Never invents or assumes missing page numbers, timestamps, or documents.
    """
    rec_id = record.get("record_id")
    case_id = record.get("case_id")
    doc_name = record.get("document_name")
    page_num = record.get("page_number")
    timestamp = record.get("timestamp")

    # Validate integer page_number
    valid_page: Optional[int] = None
    if isinstance(page_num, int) and not isinstance(page_num, bool):
        valid_page = page_num
    elif isinstance(page_num, str) and page_num.strip().isdigit():
        valid_page = int(page_num.strip())

    missing_fields: List[str] = []
    if not rec_id:
        missing_fields.append("record_id")
    if not case_id:
        missing_fields.append("case_id")
    if not doc_name:
        missing_fields.append("document_name")
    if valid_page is None:
        missing_fields.append("page_number")
    if not timestamp:
        missing_fields.append("timestamp")

    return {
        "record_id": str(rec_id) if rec_id else None,
        "case_id": str(case_id) if case_id else None,
        "document_name": str(doc_name) if doc_name else None,
        "page_number": valid_page,
        "timestamp": str(timestamp) if timestamp else None,
        "has_complete_citations": len(missing_fields) == 0,
        "missing_fields": missing_fields,
    }


def format_evidence_citation(record: Dict[str, Any]) -> str:
    """
    Generate a standardized citation label preserving source trace coordinates.
    Clearly marks missing fields as [NOT RECORDED] rather than inventing values.
    """
    citation = get_citation_metadata(record)
    case_str = citation["case_id"] or "[UNKNOWN CASE]"
    rec_str = citation["record_id"] or "[UNKNOWN RECORD]"
    doc_str = citation["document_name"] or "[NO DOCUMENT NAME]"
    page_str = str(citation["page_number"]) if citation["page_number"] is not None else "[NOT RECORDED]"
    time_str = citation["timestamp"] or "[NOT RECORDED]"

    return (
        f"[Case: {case_str} | Record: {rec_str} | "
        f"Doc: {doc_str} | Page: {page_str} | Time: {time_str}]"
    )


def normalize_record(raw_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw record dictionary into a consistent structure while preserving
    all original fields and validating citation metadata.
    Treats all incoming data strictly as passive evidence (never executable code).
    """
    normalized = dict(raw_record)

    # Standardize core identifiers
    if "record_id" in normalized and normalized["record_id"] is not None:
        normalized["record_id"] = str(normalized["record_id"]).strip()

    if "case_id" in normalized and normalized["case_id"] is not None:
        normalized["case_id"] = str(normalized["case_id"]).strip()

    if "record_type" in normalized and normalized["record_type"] is not None:
        normalized["record_type"] = str(normalized["record_type"]).strip()
    else:
        normalized["record_type"] = "unspecified"

    # Normalize numeric amount_usd if present
    amt = normalized.get("amount_usd")
    if amt is not None and not isinstance(amt, bool):
        try:
            normalized["amount_usd"] = float(Decimal(str(amt)))
        except (InvalidOperation, ValueError, TypeError):
            normalized["amount_usd"] = None
    else:
        normalized["amount_usd"] = None

    # Attach citation validation metadata
    normalized["citation_meta"] = get_citation_metadata(normalized)
    return normalized


def load_and_normalize_records(
    source: Union[str, Path, Dict[str, Any], List[Any]]
) -> List[Dict[str, Any]]:
    """
    Load records from a file path, parsed dictionary, or list, reusing the
    schema extractor from validate_data.py to support flexible structures.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Investigation data file not found: {path}")
        raw_content = path.read_text(encoding="utf-8")
        data = json.loads(raw_content)
    else:
        data = source

    _, raw_records, _, _ = _extract_cases_and_records(data)
    return [normalize_record(rec) for rec in raw_records]


def search_by_case_id(
    records: List[Dict[str, Any]],
    case_id: str,
) -> List[Dict[str, Any]]:
    """
    Filter and return only records belonging strictly to the requested case_id.
    Guarantees that records from any other case are never returned.
    """
    target = case_id.strip()
    return [rec for rec in records if rec.get("case_id") == target]


def search_text(
    records: List[Dict[str, Any]],
    query: str,
    case_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search case-insensitively across all fields in records with multi-token
    support, numeric awareness, and domain-informed entity/suspect relevance.
    If case_id is specified, strictly restricts the search scope to that case.
    Treats query purely as passive text (no regex or script execution).
    """
    import re

    target_records = search_by_case_id(records, case_id) if case_id else records
    query_clean = query.strip().lower()

    if not query_clean:
        return list(target_records)

    # Extract alphanumeric tokens
    raw_tokens = [
        re.sub(r"[^\w\-]", "", tok)
        for tok in query_clean.split()
        if len(re.sub(r"[^\w\-]", "", tok)) >= 2
    ]

    suspect_terms = {
        "suspect", "suspects", "suspected", "accused", "perpetrator", "perpetrators",
        "culprit", "culprits", "target", "targets", "person", "persons", "people",
        "individual", "individuals", "actor", "actors", "witness", "witnesses",
        "victim", "victims", "subject", "subjects", "party", "parties",
    }
    is_suspect_query = any(tok in suspect_terms for tok in raw_tokens) or (
        any(tok in ("who", "whom", "whose") for tok in raw_tokens)
        and any(tok in ("main", "prime", "primary", "involved", "responsible", "suspect", "accused", "culprit", "charged") for tok in raw_tokens)
    )

    matched: List[Dict[str, Any]] = []
    for rec in target_records:
        match_found = False

        # 1. Exact phrase / substring match across any field (preserves backward compatibility)
        for key, val in rec.items():
            if key == "citation_meta":
                continue  # skip internal metadata structure
            if isinstance(val, (str, int, float)) and query_clean in str(val).lower():
                match_found = True
                break
            elif isinstance(val, (list, tuple)):
                if any(query_clean in str(item).lower() for item in val if isinstance(item, (str, int, float))):
                    match_found = True
                    break
            elif isinstance(val, dict):
                if any(query_clean in str(v).lower() for v in val.values() if isinstance(v, (str, int, float))):
                    match_found = True
                    break

        # 2. Multi-token search across all fields of the record
        if not match_found and len(raw_tokens) >= 2:
            all_text_parts: List[str] = []
            for k, v in rec.items():
                if k == "citation_meta":
                    continue
                if isinstance(v, (str, int, float)):
                    all_text_parts.append(str(v).lower())
                elif isinstance(v, (list, tuple)):
                    all_text_parts.extend(str(item).lower() for item in v if isinstance(item, (str, int, float)))
                elif isinstance(v, dict):
                    all_text_parts.extend(str(sub_v).lower() for sub_v in v.values() if isinstance(sub_v, (str, int, float)))
            record_blob = " ".join(all_text_parts)

            meaningful = [
                t for t in raw_tokens
                if t not in ("who", "is", "the", "in", "at", "on", "of", "and", "or", "a", "an", "for", "to")
            ]
            if meaningful and all(t in record_blob for t in meaningful):
                match_found = True

        # 3. Investigation entity / suspect query matching
        if not match_found and is_suspect_query:
            rtype = str(rec.get("record_type", "")).lower()
            doc_str = str(rec.get("document_name", "")).lower()
            etype = str(rec.get("entity_type", "")).lower()
            desc = str(rec.get("description", "")).lower()

            # Person entities (resolved or mentions)
            if etype == "person" or "person" in rtype or rec.get("person_name") or rec.get("witness_name"):
                # If specific non-suspect tokens exist in query (e.g. "suspect Meera"), ensure they match
                name_tokens = [
                    t for t in raw_tokens
                    if t not in suspect_terms and t not in ("who", "is", "the", "main", "prime", "primary", "are", "tell", "me", "about")
                ]
                if not name_tokens:
                    match_found = True
                else:
                    all_fields = (
                        str(rec.get("canonical_value", "")) + " " +
                        str(rec.get("raw_value", "")) + " " +
                        str(rec.get("person_name", "")) + " " +
                        str(rec.get("witness_name", "")) + " " +
                        desc
                    ).lower()
                    if any(nt in all_fields for nt in name_tokens):
                        match_found = True

            # Foundational FIR / complaint records
            elif "fir" in doc_str or "fir" in rtype or "complaint" in doc_str:
                match_found = True

        if match_found:
            matched.append(rec)

    return matched


def filter_by_record_type(
    records: List[Dict[str, Any]],
    record_type: str,
    case_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter records by their record_type (case-insensitive).
    If case_id is provided, strictly limits results to that case.
    """
    target_records = search_by_case_id(records, case_id) if case_id else records
    target_type = record_type.strip().lower()
    return [
        rec
        for rec in target_records
        if str(rec.get("record_type", "")).strip().lower() == target_type
    ]


def get_record_by_id(
    records: List[Dict[str, Any]],
    record_id: str,
    case_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single record by exact record_id.
    If case_id is provided, enforces case isolation: returns None if the record
    belongs to a different case.
    """
    target_id = record_id.strip()
    for rec in records:
        if rec.get("record_id") == target_id:
            if case_id is not None and rec.get("case_id") != case_id.strip():
                return None  # Preserves case isolation
            return rec
    return None


def sort_records_chronologically(
    records: List[Dict[str, Any]],
    case_id: Optional[str] = None,
    descending: bool = False,
) -> List[Dict[str, Any]]:
    """
    Sort records chronologically by timestamp when timestamps are valid.
    If case_id is provided, limits records strictly to that case.
    Records with missing or unparseable timestamps are placed stably at the end.
    """
    target_records = search_by_case_id(records, case_id) if case_id else records

    valid_entries: List[Tuple[datetime, int, Dict[str, Any]]] = []
    undated_entries: List[Tuple[int, Dict[str, Any]]] = []

    for idx, rec in enumerate(target_records):
        dt = parse_iso_timestamp(rec.get("timestamp"))
        if dt is not None:
            valid_entries.append((dt, idx, rec))
        else:
            undated_entries.append((idx, rec))

    valid_entries.sort(key=lambda item: item[0], reverse=descending)

    sorted_records = [entry[2] for entry in valid_entries]
    sorted_records.extend([entry[1] for entry in undated_entries])
    return sorted_records


def calculate_case_metrics(
    records: List[Dict[str, Any]],
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate exact record counts and numeric totals deterministically in Python.
    If case_id is provided, calculations are strictly isolated to that case.
    """
    target_records = search_by_case_id(records, case_id) if case_id else records

    total_records = len(target_records)
    record_types: Counter[str] = Counter()
    total_amount_decimal = Decimal("0.00")
    records_with_amount = 0
    missing_page_count = 0
    missing_time_count = 0
    missing_doc_count = 0

    valid_dts: List[Tuple[datetime, str]] = []

    for rec in target_records:
        rtype = rec.get("record_type") or "unspecified"
        record_types[str(rtype)] += 1

        amt = rec.get("amount_usd")
        if amt is not None and not isinstance(amt, bool):
            try:
                dec_val = Decimal(str(amt))
                total_amount_decimal += dec_val
                records_with_amount += 1
            except (InvalidOperation, TypeError):
                pass

        citation = rec.get("citation_meta") or get_citation_metadata(rec)
        if citation.get("page_number") is None:
            missing_page_count += 1
        ts_val = citation.get("timestamp")
        if not ts_val:
            missing_time_count += 1
        else:
            parsed_dt = parse_iso_timestamp(ts_val)
            if parsed_dt is not None:
                valid_dts.append((parsed_dt, str(ts_val)))
        if not citation.get("document_name"):
            missing_doc_count += 1

    valid_dts.sort(key=lambda item: item[0])
    earliest_timestamp = valid_dts[0][1] if valid_dts else None
    latest_timestamp = valid_dts[-1][1] if valid_dts else None

    return {
        "case_id_scope": case_id if case_id else "ALL_CASES",
        "total_records": total_records,
        "record_type_breakdown": dict(record_types),
        "total_amount_usd": float(round(total_amount_decimal, 2)),
        "total_amount_decimal": str(round(total_amount_decimal, 2)),
        "records_with_amount": records_with_amount,
        "earliest_timestamp": earliest_timestamp,
        "latest_timestamp": latest_timestamp,
        "missing_citation_counts": {
            "missing_page_number": missing_page_count,
            "missing_timestamp": missing_time_count,
            "missing_document_name": missing_doc_count,
        },
    }


def format_safe_preview(record: Dict[str, Any]) -> str:
    """
    Format a concise, privacy-safe preview of a record containing only
    traceability coordinates, record type, and financial amount (no PII values).
    """
    citation_str = format_evidence_citation(record)
    rtype = record.get("record_type", "unspecified")
    amt = record.get("amount_usd")
    amt_str = f" | Amount: ${amt:,.2f}" if amt is not None else ""
    return f"{citation_str} [Type: {rtype}{amt_str}]"


class EvidenceSearchEngine:
    """
    Stateful retrieval engine wrapping normalized investigation records.
    """

    def __init__(
        self,
        source: Optional[Union[str, Path, Dict[str, Any], List[Any]]] = None,
    ) -> None:
        self.records: List[Dict[str, Any]] = []
        if source is not None:
            self.load(source)

    def load(
        self,
        source: Union[str, Path, Dict[str, Any], List[Any]],
    ) -> List[Dict[str, Any]]:
        self.records = load_and_normalize_records(source)
        return self.records

    def search_case(self, case_id: str) -> List[Dict[str, Any]]:
        return search_by_case_id(self.records, case_id)

    def search_text(
        self,
        query: str,
        case_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return search_text(self.records, query, case_id=case_id)

    def filter_type(
        self,
        record_type: str,
        case_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return filter_by_record_type(self.records, record_type, case_id=case_id)

    def get_by_id(
        self,
        record_id: str,
        case_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return get_record_by_id(self.records, record_id, case_id=case_id)

    def sort_chronological(
        self,
        case_id: Optional[str] = None,
        descending: bool = False,
    ) -> List[Dict[str, Any]]:
        return sort_records_chronologically(self.records, case_id=case_id, descending=descending)

    def metrics(self, case_id: Optional[str] = None) -> Dict[str, Any]:
        return calculate_case_metrics(self.records, case_id=case_id)


def main(argv: Optional[List[str]] = None) -> None:
    """CLI demonstration illustrating data-driven evidence retrieval without hardcoded cases."""
    args = argv if argv is not None else sys.argv[1:]
    data_file = Path(args[0]) if args else Path("data/mock_investigation_data.json")
    if not data_file.exists():
        print(f"Error: {data_file} not found.")
        return

    engine = EvidenceSearchEngine(data_file)
    print("============================================================")
    print(" EVIDENCE RETRIEVAL ENGINE (DATA-DRIVEN DEMONSTRATION)")
    print("============================================================")
    print(f"Dataset File Path   : {data_file}")
    print(f"Total Records Loaded: {len(engine.records)}")

    discovered_cases = sorted({str(r.get("case_id")) for r in engine.records if r.get("case_id")})
    if not discovered_cases:
        print("No cases discovered in dataset.")
        return

    sample_case = discovered_cases[0]
    print(f"\nDiscovered Cases in Dataset: {discovered_cases}")

    # 1. Case Metrics
    print(f"\n[1] Exact Python Metrics for Discovered Case '{sample_case}':")
    metrics = engine.metrics(case_id=sample_case)
    print(f"  - Total Records       : {metrics['total_records']}")
    print(f"  - Total Recorded USD  : ${metrics['total_amount_usd']:,.2f}")
    print(f"  - Record Types        : {metrics['record_type_breakdown']}")
    print(f"  - Date Range          : {metrics.get('earliest_timestamp') or '[NONE]'} to {metrics.get('latest_timestamp') or '[NONE]'}")
    print(f"  - Missing Metadata    : {metrics['missing_citation_counts']}")

    # 2. Chronological Ordering
    timeline = engine.sort_chronological(case_id=sample_case)
    print(f"\n[2] Chronological Timeline for '{sample_case}' ({len(timeline)} records):")
    for rec in timeline:
        print(f"  - {format_safe_preview(rec)}")

    print("============================================================")


if __name__ == "__main__":
    main()
