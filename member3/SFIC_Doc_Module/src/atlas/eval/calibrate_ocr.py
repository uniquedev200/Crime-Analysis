"""OCR confidence calibration and character accuracy analysis for ATLAS Dev 3.

Evaluates character error rate and accuracy across OCR confidence buckets on labelled
synthetic ground truth to calibrate OCR_ID_AUTOTRUST_MIN_CONF.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfidenceBucketResult:
    """Character accuracy metrics for a specific OCR confidence range."""

    bucket_name: str
    min_conf: float
    max_conf: float
    total_tokens: int
    total_chars: int
    matching_chars: int
    char_accuracy: float
    char_error_rate: float


def compute_char_level_accuracy(predicted: str, truth: str) -> tuple[int, int]:
    """Compute number of matching characters and total truth characters (Levenshtein/alignment)."""
    if not truth:
        return (0, len(predicted))

    matches = 0
    # Simple character alignment / positional match for identifier token calibration
    min_len = min(len(predicted), len(truth))
    for p_ch, t_ch in zip(predicted[:min_len], truth[:min_len], strict=False):
        if p_ch == t_ch:
            matches += 1

    return matches, len(truth)


def calibrate_ocr(
    token_records: list[dict[str, Any]] | None = None,
    target_accuracy_threshold: float = 0.995,
) -> dict[str, Any]:
    """Calibrate OCR confidence buckets against labelled identifier ground truth tokens.

    Args:
        token_records: List of dicts with 'ocr_token', 'truth_token', and 'confidence' (0-100).
        target_accuracy_threshold: Minimum accuracy to recommend autotrust threshold.

    Returns:
        Dictionary with bucket breakdown, overall accuracy, and recommended threshold.
    """
    if not token_records:
        return {
            "status": "insufficient_data",
            "buckets": {},
            "overall_char_accuracy": 0.0,
            "recommended_autotrust_threshold": None,
            "note": "OCR_ID_AUTOTRUST_MIN_CONF disabled by default (null). Requires labelled OCR data.",
        }

    # Define standard confidence buckets
    bucket_defs = [
        ("0_50", 0.0, 50.0),
        ("50_70", 50.0, 70.0),
        ("70_85", 70.0, 85.0),
        ("85_95", 85.0, 95.0),
        ("95_100", 95.0, 100.0),
    ]

    bucket_stats: dict[str, dict[str, Any]] = {
        name: {"tokens": 0, "chars": 0, "matches": 0, "min": low, "max": high} for name, low, high in bucket_defs
    }

    total_chars = 0
    total_matches = 0

    for rec in token_records:
        ocr_token = str(rec.get("ocr_token", "")).strip()
        truth_token = str(rec.get("truth_token", "")).strip()
        conf = float(rec.get("confidence", 0.0))

        matches, chars = compute_char_level_accuracy(ocr_token, truth_token)
        total_matches += matches
        total_chars += chars

        for name, low, high in bucket_defs:
            if (conf >= low and conf < high) or (high == 100.0 and conf == 100.0):
                bucket_stats[name]["tokens"] += 1
                bucket_stats[name]["chars"] += chars
                bucket_stats[name]["matches"] += matches
                break

    results_by_bucket: dict[str, dict[str, Any]] = {}
    recommended_min_conf: float | None = None

    for name, stats in bucket_stats.items():
        n_chars = stats["chars"]
        n_matches = stats["matches"]
        acc = round(n_matches / n_chars, 4) if n_chars > 0 else 0.0
        cer = round(1.0 - acc, 4) if n_chars > 0 else 0.0

        results_by_bucket[name] = {
            "range": f"[{stats['min']}, {stats['max']}]",
            "token_count": stats["tokens"],
            "char_count": n_chars,
            "matching_chars": n_matches,
            "char_accuracy": acc,
            "char_error_rate": cer,
        }

        # If a bucket reaches the stringent target threshold (default 99.5%)
        if acc >= target_accuracy_threshold and recommended_min_conf is None and n_chars >= 50:
            recommended_min_conf = float(stats["min"])

    overall_acc = round(total_matches / total_chars, 4) if total_chars > 0 else 0.0

    return {
        "status": "calibrated",
        "total_records": len(token_records),
        "overall_char_accuracy": overall_acc,
        "buckets": results_by_bucket,
        "recommended_autotrust_threshold": recommended_min_conf,
        "note": "Per PLAN 5.5, OCR-derived identifiers require human review unless autotrust is explicitly enabled.",
    }


__all__ = [
    "ConfidenceBucketResult",
    "calibrate_ocr",
    "compute_char_level_accuracy",
]
