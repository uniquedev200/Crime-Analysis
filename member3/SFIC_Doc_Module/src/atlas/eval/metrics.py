"""Evaluation metrics calculation for ATLAS Dev 3 extraction pipeline.

Calculates precision, recall, F1 by entity type, exact match accuracy for
identifiers, quote rejection rates, OCR identifier review rates, and timings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricScores:
    """Precision, recall, and F1 score container."""

    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def compute_precision_recall_f1(tp: int, fp: int, fn: int) -> MetricScores:
    """Compute precision, recall, and harmonic F1 from count values."""
    precision = (1.0 if fn == 0 else 0.0) if tp + fp == 0 else tp / (tp + fp)
    recall = (1.0 if fp == 0 else 0.0) if tp + fn == 0 else tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0.0 else (2.0 * precision * recall) / (precision + recall)

    return MetricScores(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
    )


def eval_exact_match_accuracy(predicted_values: list[str], truth_values: list[str]) -> float:
    """Calculate exact match percentage between predicted and truth identifier lists."""
    if not truth_values:
        return 1.0 if not predicted_values else 0.0

    matches = 0
    remaining_truth = list(truth_values)
    for p in predicted_values:
        if p in remaining_truth:
            matches += 1
            remaining_truth.remove(p)

    return round(matches / max(len(truth_values), len(predicted_values)), 4)


def eval_quote_rejection_rate(total_model_items: int, rejected_quotes: int) -> float:
    """Compute quote rejection rate as fraction of rejected items over total extracted items."""
    if total_model_items <= 0:
        return 0.0
    return round(min(rejected_quotes / total_model_items, 1.0), 4)


def eval_ocr_id_review_rate(total_identifiers: int, review_required_identifiers: int) -> float:
    """Compute fraction of OCR-derived identifiers flagged as review_required."""
    if total_identifiers <= 0:
        return 0.0
    return round(min(review_required_identifiers / total_identifiers, 1.0), 4)


def eval_mentions_precision_recall(
    predicted_mentions: list[dict[str, Any]],
    truth_mentions: list[dict[str, Any]],
    match_key: str = "normalized_value",
) -> dict[str, Any]:
    """Calculate precision, recall, and F1 per entity type and macro/micro aggregates."""
    # Group by entity type
    all_types = sorted(
        {m.get("type", "UNKNOWN") for m in predicted_mentions} | {m.get("type", "UNKNOWN") for m in truth_mentions}
    )

    by_type: dict[str, dict[str, Any]] = {}
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for etype in all_types:
        preds = [m for m in predicted_mentions if m.get("type") == etype]
        truths = [m for m in truth_mentions if m.get("type") == etype]

        truth_keys = [str(t.get(match_key) or t.get("surface_text", "")).strip().lower() for t in truths]
        pred_keys = [str(p.get(match_key) or p.get("surface_text", "")).strip().lower() for p in preds]

        tp = 0
        rem_truth = list(truth_keys)
        for pk in pred_keys:
            if pk in rem_truth:
                tp += 1
                rem_truth.remove(pk)

        fp = len(pred_keys) - tp
        fn = len(truth_keys) - tp

        total_tp += tp
        total_fp += fp
        total_fn += fn

        scores = compute_precision_recall_f1(tp, fp, fn)
        by_type[etype] = {
            "precision": scores.precision,
            "recall": scores.recall,
            "f1": scores.f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "pred_count": len(preds),
            "truth_count": len(truths),
        }

    overall = compute_precision_recall_f1(total_tp, total_fp, total_fn)

    return {
        "overall": {
            "precision": overall.precision,
            "recall": overall.recall,
            "f1": overall.f1,
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
        },
        "by_type": by_type,
    }


__all__ = [
    "MetricScores",
    "compute_precision_recall_f1",
    "eval_exact_match_accuracy",
    "eval_mentions_precision_recall",
    "eval_ocr_id_review_rate",
    "eval_quote_rejection_rate",
]
