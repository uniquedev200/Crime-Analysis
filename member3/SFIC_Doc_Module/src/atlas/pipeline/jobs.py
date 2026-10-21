"""Job state tracking, run enumeration, and state evaluation logic.

Implements PLAN.md Section 5.9 Job state rules:
- All chunks OK and no rejections/review -> completed
- Any rejections, review items or failed chunks (with >= 1 chunk OK) -> completed_with_warnings
- All chunks failed -> failed
- Final CaseResult fails Pydantic validation -> failed_validation
- Input refused -> rejected_input
"""

from __future__ import annotations

from pathlib import Path

from atlas.contracts.enums import JobState
from atlas.contracts.ids import validate_case_id


def list_runs(case_id: str, output_dir: Path | str = "./outputs") -> list[str]:
    """Return sorted list of run IDs for a case, most recent first."""
    validate_case_id(case_id)
    base_dir = Path(output_dir) / case_id
    if not base_dir.is_dir():
        return []

    run_dirs = [d.name for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("RUN-")]
    # RUN-YYYYMMDDTHHMMSSZ-<6hex> sorts lexicographically by timestamp
    run_dirs.sort(reverse=True)
    return run_dirs


def compute_job_state(
    *,
    chunks_total: int = 0,
    chunks_failed: int = 0,
    review_items_count: int = 0,
    rejections_count: int = 0,
    warnings_count: int = 0,
    input_refused: bool = False,
    validation_failed: bool = False,
) -> JobState:
    """Determine the top-level JobState strictly per PLAN.md Section 5.9 rules."""
    if input_refused:
        return JobState.REJECTED_INPUT

    if validation_failed:
        return JobState.FAILED_VALIDATION

    if chunks_total > 0 and chunks_failed >= chunks_total:
        return JobState.FAILED

    if chunks_failed > 0 or review_items_count > 0 or rejections_count > 0 or warnings_count > 0:
        return JobState.COMPLETED_WITH_WARNINGS

    return JobState.COMPLETED


__all__ = ["compute_job_state", "list_runs"]
