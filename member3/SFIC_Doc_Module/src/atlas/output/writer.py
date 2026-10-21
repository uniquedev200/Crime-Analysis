"""Output writer for ATLAS Dev 3 run outputs.

Implements PLAN.md Section 4.5 and H3 specifications:
Creates directory outputs/{case_id}/{run_id}/ and writes:
- result.json (valid CaseResult with schema_version="1.0.0")
- events.jsonl (one Event per line, sorted)
- review_queue.json (list of ReviewItem records)
- receipt.json (intake receipt and run metadata)
- trace.jsonl (stages, timings, counts, ids - scrubbed of PII)

All JSON files are written with ensure_ascii=False, indent=2, and encoding='utf-8'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atlas.contracts.records import CaseResult, Event


class OutputWriter:
    """Writes all run output artifacts to outputs/{case_id}/{run_id}/."""

    def __init__(self, base_output_dir: Path | str = "./outputs") -> None:
        self.base_output_dir = Path(base_output_dir)

    def write_all(
        self,
        case_result: CaseResult,
        trace_entries: list[dict[str, Any]] | None = None,
        receipts: list[dict[str, Any]] | None = None,
        output_dir: Path | str | None = None,
        bulk_events: list[Event] | None = None,
    ) -> Path:
        """Write all output artifacts for a completed or failed case run.

        Args:
            case_result: Completed CaseResult model instance.
            trace_entries: Optional sequence of stage timing and count trace records.
            receipts: Optional raw document intake receipts.
            output_dir: Optional override for base output directory.
            bulk_events: Optional list of bulk tabular events (CDR/bank) to include in events.jsonl.

        Returns:
            Path to the created run directory: outputs/{case_id}/{run_id}/.
        """
        base_dir = Path(output_dir) if output_dir is not None else self.base_output_dir
        run_dir = base_dir / case_result.case_id / case_result.run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. result.json (CaseResult)
        result_file = run_dir / "result.json"
        result_dict = case_result.model_dump(mode="json")
        result_json = json.dumps(result_dict, indent=2, ensure_ascii=False)
        result_file.write_text(result_json, encoding="utf-8")

        # 2. events.jsonl (all events, sorted deterministically)
        events_file = run_dir / "events.jsonl"
        combined_events = list(case_result.events)
        if bulk_events:
            combined_events.extend(bulk_events)

        # Deduplicate and sort events deterministically by time then event_id
        unique_events: dict[str, Event] = {e.event_id: e for e in combined_events}
        sorted_events = sorted(
            unique_events.values(),
            key=lambda e: (
                e.time.normalized_iso if e.time and e.time.normalized_iso else "",
                e.time.original_text if e.time else "",
                e.event_id,
            ),
        )

        with events_file.open("w", encoding="utf-8") as f:
            for ev in sorted_events:
                ev_line = json.dumps(ev.model_dump(mode="json"), ensure_ascii=False)
                f.write(ev_line + "\n")

        # 3. review_queue.json
        review_file = run_dir / "review_queue.json"
        review_dicts = [item.model_dump(mode="json") for item in case_result.review_items]
        review_file.write_text(json.dumps(review_dicts, indent=2, ensure_ascii=False), encoding="utf-8")

        # 4. receipt.json
        receipt_file = run_dir / "receipt.json"
        doc_receipts = receipts
        if doc_receipts is None:
            doc_receipts = [doc.model_dump(mode="json") for doc in case_result.documents]

        receipt_payload = {
            "case_id": case_result.case_id,
            "run_id": case_result.run.run_id,
            "idempotency_key": case_result.run.idempotency_key,
            "run_meta": case_result.run.model_dump(mode="json"),
            "documents": doc_receipts,
        }
        receipt_file.write_text(json.dumps(receipt_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        # 5. trace.jsonl (PII-free stage, timings, counts, IDs)
        trace_file = run_dir / "trace.jsonl"
        safe_trace = self._scrub_trace_entries(trace_entries or [])
        with trace_file.open("w", encoding="utf-8") as f:
            for entry in safe_trace:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return run_dir

    def _scrub_trace_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ensure trace entries contain only metadata: stages, timings, counts, and IDs."""
        safe_keys = {
            "timestamp",
            "stage",
            "duration_ms",
            "status",
            "case_id",
            "run_id",
            "doc_id",
            "file_sha256",
            "chunk_idx",
            "units_count",
            "mentions_count",
            "relationships_count",
            "events_count",
            "aggregates_count",
            "review_items_count",
            "rejections_count",
            "error_type",
        }
        scrubbed = []
        for entry in entries:
            clean_entry = {k: v for k, v in entry.items() if k in safe_keys}
            scrubbed.append(clean_entry)
        return scrubbed


__all__ = ["OutputWriter"]
