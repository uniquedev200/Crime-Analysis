"""Deterministic ID generation and validation helpers for ATLAS Dev 3.

All ID helpers use UTF-8 string encoding and hashlib (sha1/sha256).
Run IDs use UTC timestamp without colons for Windows filesystem safety.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Sequence
from datetime import datetime

CASE_ID_REGEX = r"^[A-Za-z0-9_-]{1,64}$"
CASE_ID_PATTERN = re.compile(CASE_ID_REGEX)


def validate_case_id(case_id: str) -> str:
    """Validate case_id against regex ^[A-Za-z0-9_-]{1,64}$.

    Enforced to block path traversal and injection attacks at ingestion gate.
    Raises ValueError if invalid. Returns case_id when valid.
    """
    if not isinstance(case_id, str):
        raise ValueError(f"case_id must be a string, got {type(case_id).__name__}")
    if not CASE_ID_PATTERN.match(case_id):
        raise ValueError(f"Invalid case_id '{case_id}': must match regex {CASE_ID_REGEX}")
    return case_id


def make_doc_id(sha256: str) -> str:
    """Generate deterministic document ID from content SHA-256 hash."""
    clean_hash = sha256.lower().strip()
    return f"DOC-{clean_hash[:12]}"


def make_unit_id_page(doc_id: str, page: int) -> str:
    """Generate unit ID for a document page: {doc_id}:p{page:03d}."""
    return f"{doc_id}:p{page:03d}"


def make_unit_id_line(doc_id: str, page: int, line: int) -> str:
    """Generate unit ID for a specific line on a page: {doc_id}:p{page:03d}:l{line:03d}."""
    return f"{doc_id}:p{page:03d}:l{line:03d}"


def make_unit_id_row(doc_id: str, sheet_index: int, row: int) -> str:
    """Generate unit ID for a table row: {doc_id}:s{sheet_index:02d}:r{row:06d}."""
    return f"{doc_id}:s{sheet_index:02d}:r{row:06d}"


def make_unit_id_text_line(doc_id: str, line: int) -> str:
    """Generate unit ID for a plain text file line: {doc_id}:l{line:06d}."""
    return f"{doc_id}:l{line:06d}"


def make_unit_id_json(doc_id: str, json_pointer: str) -> str:
    """Generate unit ID for a JSON pointer field: {doc_id}:j:{json_pointer}."""
    clean_pointer = json_pointer.lstrip("/")
    return f"{doc_id}:j:{clean_pointer}"


def make_mention_id(
    doc_id: str,
    unit_id: str,
    type_str: str,
    normalized_or_surface: str,
    occurrence_index: int | str = 0,
) -> str:
    """Generate deterministic mention ID: 'M-' + sha1(doc_id|unit_id|type|value|idx)[:12]."""
    payload = f"{doc_id}|{unit_id}|{type_str}|{normalized_or_surface}|{occurrence_index}".encode()
    return f"M-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_rel_id(
    doc_id: str,
    unit_id: str,
    type_str: str,
    subject_mention_id: str,
    object_mention_id: str,
    occurrence_index: int | str = 0,
) -> str:
    """Generate deterministic relationship ID: 'R-' + sha1(...)[:12]."""
    payload = f"{doc_id}|{unit_id}|{type_str}|{subject_mention_id}|{object_mention_id}|{occurrence_index}".encode()
    return f"R-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_event_id(
    doc_id: str,
    unit_id: str,
    type_str: str,
    description_or_time: str = "",
    occurrence_index: int | str = 0,
) -> str:
    """Generate deterministic event ID: 'E-' + sha1(...)[:12]."""
    if isinstance(description_or_time, int) and occurrence_index == 0:
        occurrence_index = description_or_time
        description_or_time = ""
    payload = f"{doc_id}|{unit_id}|{type_str}|{description_or_time}|{occurrence_index}".encode()
    return f"E-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_aggregate_id(
    case_id: str,
    type_str: str,
    subject_mention_id: str,
    object_mention_id: str,
) -> str:
    """Generate deterministic aggregate ID: 'AGG-' + sha1(...)[:12]."""
    payload = f"{case_id}|{type_str}|{subject_mention_id}|{object_mention_id}".encode()
    return f"AGG-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_review_id(
    case_id: str,
    kind: str,
    target_id: str,
    detail: str = "",
) -> str:
    """Generate deterministic review item ID: 'REV-' + sha1(...)[:12]."""
    payload = f"{case_id}|{kind}|{target_id}|{detail}".encode()
    return f"REV-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_rejection_id(
    case_id: str,
    doc_id: str,
    kind: str,
    reason: str,
    occurrence_index: int | str = 0,
) -> str:
    """Generate deterministic rejection item ID: 'REJ-' + sha1(...)[:12]."""
    payload = f"{case_id}|{doc_id}|{kind}|{reason}|{occurrence_index}".encode()
    return f"REJ-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_suggestion_id(
    case_id: str,
    mention_id: str,
    candidate_entity_id: str,
) -> str:
    """Generate deterministic resolution suggestion ID: 'SUG-' + sha1(...)[:12]."""
    payload = f"{case_id}|{mention_id}|{candidate_entity_id}".encode()
    return f"SUG-{hashlib.sha1(payload).hexdigest()[:12]}"


def make_action_id() -> str:
    """Generate unique review action ID: 'ACT-' + 12 hex characters."""
    return f"ACT-{secrets.token_hex(6)}"


def make_run_id() -> str:
    """Generate Windows-filesystem safe run ID: RUN-YYYYMMDDTHHMMSSZ-<6hex> (no colons)."""
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    random_hex = secrets.token_hex(3)  # 3 bytes = 6 hex chars
    return f"RUN-{now_str}-{random_hex}"


def make_idempotency_key(
    file_sha256: str,
    pipeline_version: str,
    ocr_engine: str,
    ocr_version: str,
    ocr_langs: str | Sequence[str],
    provider: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    normalization_version: str,
) -> str:
    """Generate 64-hex SHA-256 idempotency key for a run configuration and source file."""
    langs_str = "+".join(ocr_langs) if isinstance(ocr_langs, (list, tuple)) else str(ocr_langs)

    parts = [
        str(file_sha256),
        str(pipeline_version),
        str(ocr_engine),
        str(ocr_version),
        langs_str,
        str(provider),
        str(model),
        str(prompt_version),
        str(schema_version),
        str(normalization_version),
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def safe_filename(name: str, replacement: str = "_") -> str:
    """Replace colons, plus signs, and other filesystem-unsafe characters with replacement string."""
    # Windows/POSIX unsafe: : + < > " / \ | ? * and ASCII control characters 0x00-0x1F
    unsafe_pattern = re.compile(r'[:+<>"\/\\|?*\x00-\x1f]')
    sanitized = unsafe_pattern.sub(replacement, name)
    if replacement:
        sanitized = re.sub(f"{re.escape(replacement)}+", replacement, sanitized)
    return sanitized


__all__ = [
    "CASE_ID_PATTERN",
    "CASE_ID_REGEX",
    "make_action_id",
    "make_aggregate_id",
    "make_doc_id",
    "make_event_id",
    "make_idempotency_key",
    "make_mention_id",
    "make_rejection_id",
    "make_rel_id",
    "make_review_id",
    "make_run_id",
    "make_suggestion_id",
    "make_unit_id_json",
    "make_unit_id_line",
    "make_unit_id_page",
    "make_unit_id_row",
    "make_unit_id_text_line",
    "safe_filename",
    "validate_case_id",
]
