"""Evaluation runner comparing pipeline extraction outputs against ground truth datasets.

Produces structured performance evaluation metrics across mentions, relationships,
events, review items, and identifier accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas.eval.metrics import (
    compute_precision_recall_f1,
    eval_exact_match_accuracy,
    eval_mentions_precision_recall,
    eval_ocr_id_review_rate,
    eval_quote_rejection_rate,
)


class EvalRunner:
    """Evaluates case extraction outputs against synthetic ground truth."""

    def __init__(self, truth_dir: Path | None = None) -> None:
        self.truth_dir = truth_dir

    def load_truth_for_case(self, case_id: str) -> dict[str, Any]:
        """Aggregate truth files for a specific case_id."""
        if not self.truth_dir or not self.truth_dir.is_dir():
            return {"mentions": [], "relationships": [], "events": [], "review_items": []}

        case_mentions: list[dict[str, Any]] = []
        case_relationships: list[dict[str, Any]] = []
        case_events: list[dict[str, Any]] = []
        case_review_items: list[dict[str, Any]] = []

        for truth_file in sorted(self.truth_dir.glob("*.truth.json")):
            try:
                data = json.loads(truth_file.read_text(encoding="utf-8"))
                if data.get("case_id") == case_id:
                    case_mentions.extend(data.get("mentions", []))
                    case_relationships.extend(data.get("relationships", []))
                    case_events.extend(data.get("events", []))
                    case_review_items.extend(data.get("review_items", []))
            except Exception:
                continue

        return {
            "case_id": case_id,
            "mentions": case_mentions,
            "relationships": case_relationships,
            "events": case_events,
            "review_items": case_review_items,
        }

    def evaluate_case(
        self,
        case_result: dict[str, Any],
        truth: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute comprehensive evaluation metrics comparing result against truth."""
        pred_mentions = case_result.get("mentions", [])
        truth_mentions = truth.get("mentions", [])

        mention_eval = eval_mentions_precision_recall(pred_mentions, truth_mentions)

        # Identifier exact match accuracy
        id_types = {"PHONE", "IMEI", "VEHICLE", "ACCOUNT"}
        pred_ids = [
            str(m.get("normalized_value") or m.get("surface_text", "")).strip()
            for m in pred_mentions
            if m.get("type") in id_types
        ]
        truth_ids = [
            str(m.get("normalized_value") or m.get("surface_text", "")).strip()
            for m in truth_mentions
            if m.get("type") in id_types
        ]
        id_exact_match = eval_exact_match_accuracy(pred_ids, truth_ids)

        # Rejection & Review rates
        rejections = case_result.get("rejections", [])
        total_items = len(pred_mentions) + len(case_result.get("relationships", [])) + len(rejections)
        quote_rej_rate = eval_quote_rejection_rate(total_items, len(rejections))

        ocr_ids = [m for m in pred_mentions if m.get("type") in id_types and m.get("origin") == "ocr"]
        review_ocr_ids = [m for m in ocr_ids if m.get("identifier_trust") == "review_required"]
        ocr_review_rate = eval_ocr_id_review_rate(len(ocr_ids), len(review_ocr_ids))

        # Relationships
        pred_rels = case_result.get("relationships", [])
        truth_rels = truth.get("relationships", [])
        rel_eval = self._eval_items_precision_recall(pred_rels, truth_rels, "type")

        # Events
        pred_events = case_result.get("events", [])
        truth_events = truth.get("events", [])
        event_eval = self._eval_items_precision_recall(pred_events, truth_events, "type")

        return {
            "case_id": case_result.get("case_id", truth.get("case_id", "UNKNOWN")),
            "mentions": mention_eval,
            "relationships": rel_eval,
            "events": event_eval,
            "identifier_exact_match_accuracy": id_exact_match,
            "quote_rejection_rate": quote_rej_rate,
            "ocr_identifier_review_rate": ocr_review_rate,
        }

    @staticmethod
    def _eval_items_precision_recall(
        pred_items: list[dict[str, Any]],
        truth_items: list[dict[str, Any]],
        type_key: str = "type",
    ) -> dict[str, Any]:
        """Generic item precision/recall evaluation by type."""
        pred_types = [str(item.get(type_key, "UNKNOWN")).strip() for item in pred_items]
        truth_types = [str(item.get(type_key, "UNKNOWN")).strip() for item in truth_items]

        tp = 0
        rem_truth = list(truth_types)
        for pt in pred_types:
            if pt in rem_truth:
                tp += 1
                rem_truth.remove(pt)

        fp = len(pred_types) - tp
        fn = len(truth_types) - tp

        scores = compute_precision_recall_f1(tp, fp, fn)
        return {
            "precision": scores.precision,
            "recall": scores.recall,
            "f1": scores.f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "pred_count": len(pred_items),
            "truth_count": len(truth_items),
        }


__all__ = ["EvalRunner"]
