"""Deterministic CSV reader for tabular evidence.

Implements PLAN.md section 5.7:
- Built-in csv module.
- utf-8-sig encoding with fallback to latin-1 (emitting a warning).
- Sniff delimiter among ',', ';', '\t', '|'.
- Every value read strictly as str.
- Blank rows preserved with is_blank=True.
- Ragged rows emit a warning containing the physical row number and are never dropped.
- Returns {headers, rows, warnings, delimiter}.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

ALLOWED_DELIMITERS = [",", ";", "\t", "|"]


def sniff_delimiter(sample: str) -> str:
    """Sniff CSV delimiter among ',', ';', '\t', '|'."""
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=";,|\t")
        if dialect.delimiter in ALLOWED_DELIMITERS:
            return dialect.delimiter
    except Exception:
        pass

    # Heuristic count of candidates in first non-empty line
    for line in sample.splitlines():
        clean = line.strip()
        if clean:
            counts = {d: clean.count(d) for d in ALLOWED_DELIMITERS}
            best = max(counts, key=counts.get)  # type: ignore[arg-type]
            if counts[best] > 0:
                return best
            break

    return ","


def read_csv(path: Path | str, encoding: str = "utf-8-sig") -> dict[str, Any]:
    """Read a CSV file deterministically into headers, rows, warnings, and delimiter.

    Physical row numbers count the header as row 1. Data rows start at row 2.
    """
    file_path = Path(path)
    warnings: list[str] = []

    # Read bytes and decode with fallback
    raw_bytes = file_path.read_bytes()
    try:
        content = raw_bytes.decode(encoding)
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1")
        warnings.append(f"Encoding fallback: latin-1 used instead of {encoding}")

    if not content.strip():
        return {
            "headers": [],
            "rows": [],
            "warnings": warnings,
            "delimiter": ",",
        }

    # Delimiter sniffing
    sample = content[:8192]
    delimiter = sniff_delimiter(sample)

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)

    headers: list[str] = []
    rows: list[dict[str, Any]] = []

    row_idx = 0
    for record in reader:
        row_idx += 1  # 1-indexed physical record number

        if row_idx == 1:
            headers = [h.strip() for h in record]
            continue

        str_record = [str(cell) for cell in record]
        is_blank = len(str_record) == 0 or all(cell.strip() == "" for cell in str_record)

        if not is_blank and len(str_record) != len(headers):
            warnings.append(f"Ragged row at row {row_idx}: expected {len(headers)} columns, got {len(str_record)}")

        # Build row dict mapping headers
        values_dict: dict[str, str] = {}
        for h_idx, h_name in enumerate(headers):
            if h_idx < len(str_record):
                values_dict[h_name] = str_record[h_idx]
            else:
                values_dict[h_name] = ""

        row_item: dict[str, Any] = {
            "row_num": row_idx,
            "is_blank": is_blank,
            "values": values_dict,
            "raw": str_record,
        }
        # Also provide direct key access for convenience
        for k, v in values_dict.items():
            if k not in row_item:
                row_item[k] = v

        rows.append(row_item)

    return {
        "headers": headers,
        "rows": rows,
        "warnings": warnings,
        "delimiter": delimiter,
    }


__all__ = ["read_csv", "sniff_delimiter"]
