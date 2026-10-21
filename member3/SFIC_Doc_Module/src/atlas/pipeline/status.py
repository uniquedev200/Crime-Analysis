"""Status and results retrieval helpers for ATLAS Dev 3 pipeline runs.

Provides helpers to read latest run status and load CaseResult models for a given case_id.
All file reads strictly use encoding='utf-8'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas.contracts.enums import JobState
from atlas.contracts.ids import validate_case_id
from atlas.contracts.records import CaseResult, ReviewItem
from atlas.pipeline.jobs import list_runs


def get_latest_run_id(case_id: str, output_dir: Path | str = "./outputs") -> str | None:
    """Return latest run_id for case_id or None if no runs exist."""
    runs = list_runs(case_id, output_dir=output_dir)
    return runs[0] if runs else None


def load_case_result(
    case_id: str,
    run_id: str | None = None,
    output_dir: Path | str = "./outputs",
) -> CaseResult | None:
    """Load CaseResult from outputs/{case_id}/{run_id}/result.json."""
    validate_case_id(case_id)
    target_run = run_id or get_latest_run_id(case_id, output_dir=output_dir)
    if not target_run:
        return None

    result_file = Path(output_dir) / case_id / target_run / "result.json"
    if not result_file.is_file():
        return None

    content = result_file.read_text(encoding="utf-8")
    data = json.loads(content)
    return CaseResult.model_validate(data)


def get_case_status(
    case_id: str,
    run_id: str | None = None,
    output_dir: Path | str = "./outputs",
) -> JobState | None:
    """Return JobState of the specified or latest run for a given case."""
    result = load_case_result(case_id, run_id=run_id, output_dir=output_dir)
    return result.state if result else None


def load_review_queue(
    case_id: str,
    run_id: str | None = None,
    output_dir: Path | str = "./outputs",
) -> list[ReviewItem]:
    """Load list of ReviewItems from outputs/{case_id}/{run_id}/review_queue.json."""
    validate_case_id(case_id)
    target_run = run_id or get_latest_run_id(case_id, output_dir=output_dir)
    if not target_run:
        return []

    review_file = Path(output_dir) / case_id / target_run / "review_queue.json"
    if not review_file.is_file():
        return []

    content = review_file.read_text(encoding="utf-8")
    items_raw = json.loads(content)
    if not isinstance(items_raw, list):
        return []

    return [ReviewItem.model_validate(item) for item in items_raw]


def load_receipt(
    case_id: str,
    run_id: str | None = None,
    output_dir: Path | str = "./outputs",
) -> dict[str, Any] | None:
    """Load receipt dictionary from outputs/{case_id}/{run_id}/receipt.json."""
    validate_case_id(case_id)
    target_run = run_id or get_latest_run_id(case_id, output_dir=output_dir)
    if not target_run:
        return None

    receipt_file = Path(output_dir) / case_id / target_run / "receipt.json"
    if not receipt_file.is_file():
        return None

    content = receipt_file.read_text(encoding="utf-8")
    raw = json.loads(content)
    return raw if isinstance(raw, dict) else None


__all__ = [
    "get_case_status",
    "get_latest_run_id",
    "load_case_result",
    "load_receipt",
    "load_review_queue",
]
