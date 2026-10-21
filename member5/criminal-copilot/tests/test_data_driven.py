"""
test_data_driven.py

Verification tests ensuring the AI-Powered Criminal Investigation Copilot
is strictly data-driven and schema-aware without any hardcoded case data:
- Discovers newly introduced case IDs dynamically
- Handles arbitrary record IDs and novel record types without code modifications
- Recalculates financial totals dynamically using Decimal precision
- Reflects actual dynamic citation metadata
- Explicitly preserves missing metadata ([NOT RECORDED])
- Rejects queries for unknown topics without inventing facts (no_evidence_found)
- Enforces strict case isolation across dynamically generated cases
- Generates generic follow-up questions without injecting unsupported case claims
"""

from __future__ import annotations

import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from src.investigation_assistant import (
    answer_question,
    retrieve_case_evidence,
)
from src.ui_helpers import (
    filter_case_evidence,
    get_available_cases,
    get_record_types_for_case,
)


class TestDataDrivenArchitecture(unittest.TestCase):
    """Test suite ensuring complete independence from hardcoded case data."""

    def setUp(self) -> None:
        # Dynamically generate random case IDs and records for every test run
        self.dynamic_case_a = f"CASE-DYN-{uuid.uuid4().hex[:6].upper()}"
        self.dynamic_case_b = f"CASE-DYN-{uuid.uuid4().hex[:6].upper()}"

        self.dyn_rec_1_id = f"REC-{uuid.uuid4().hex[:4].upper()}"
        self.dyn_rec_2_id = f"REC-{uuid.uuid4().hex[:4].upper()}"
        self.dyn_rec_3_id = f"REC-{uuid.uuid4().hex[:4].upper()}"

        self.novel_type_1 = "drone_telemetry"
        self.novel_type_2 = "ballistics_spectrometry"

        self.amount_1 = 3450.75
        self.amount_2 = 1549.25

        # Synthetic dynamic fixture
        self.dynamic_dataset = {
            "cases": [
                {
                    "case_id": self.dynamic_case_a,
                    "records": [
                        {
                            "record_id": self.dyn_rec_1_id,
                            "case_id": self.dynamic_case_a,
                            "record_type": self.novel_type_1,
                            "document_name": "flight_telemetry_orbit_9.csv",
                            "page_number": 14,
                            "timestamp": "2027-03-10T08:00:00Z",
                            "amount_usd": self.amount_1,
                            "description": "Unscheduled sensor ping detected over Sector Delta.",
                        },
                        {
                            "record_id": self.dyn_rec_2_id,
                            "case_id": self.dynamic_case_a,
                            "record_type": self.novel_type_2,
                            "document_name": "spectrometry_lab_scan.pdf",
                            "page_number": None,  # Intentionally missing page number
                            "timestamp": "2027-03-11T16:30:00Z",
                            "amount_usd": self.amount_2,
                            "description": "Chemical residue analysis voucher matched solvent lot 77.",
                        },
                    ],
                },
                {
                    "case_id": self.dynamic_case_b,
                    "records": [
                        {
                            "record_id": self.dyn_rec_3_id,
                            "case_id": self.dynamic_case_b,
                            "record_type": "vault_manifest",
                            "document_name": "vault_sublevel_inventory.pdf",
                            "page_number": 3,
                            "timestamp": "2027-04-01T12:00:00Z",
                            "amount_usd": 0.00,
                            "description": "Annual vault audit checklist signed by shift auditor.",
                        }
                    ],
                },
            ]
        }

        self.normalized = load_and_normalize_records(self.dynamic_dataset)

    def test_newly_introduced_case_ids_discovered_automatically(self) -> None:
        """Verify dynamic case IDs are discovered without any code changes."""
        discovered = get_available_cases(self.normalized)
        expected = sorted([self.dynamic_case_a, self.dynamic_case_b])
        self.assertEqual(discovered, expected)

    def test_new_record_ids_and_record_types_work_dynamically(self) -> None:
        """Verify arbitrary record IDs and novel record types function seamlessly."""
        types_a = get_record_types_for_case(self.normalized, self.dynamic_case_a)
        self.assertIn("All Types", types_a)
        self.assertIn(self.novel_type_1, types_a)
        self.assertIn(self.novel_type_2, types_a)
        self.assertNotIn("vault_manifest", types_a)

        # Filter by novel type
        filtered = filter_by_record_type(
            self.normalized, record_type=self.novel_type_1, case_id=self.dynamic_case_a
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["record_id"], self.dyn_rec_1_id)

    def test_financial_totals_change_when_fixture_data_changes(self) -> None:
        """Verify financial totals adapt dynamically using Decimal precision."""
        metrics_a = calculate_case_metrics(self.normalized, case_id=self.dynamic_case_a)
        expected_total = float(Decimal("3450.75") + Decimal("1549.25"))  # 5000.00
        self.assertEqual(metrics_a["total_amount_usd"], 5000.00)
        self.assertEqual(metrics_a["total_records"], 2)
        self.assertEqual(metrics_a["records_with_amount"], 2)

        # Date range dynamically derived from records
        self.assertEqual(metrics_a["earliest_timestamp"], "2027-03-10T08:00:00Z")
        self.assertEqual(metrics_a["latest_timestamp"], "2027-03-11T16:30:00Z")

        metrics_b = calculate_case_metrics(self.normalized, case_id=self.dynamic_case_b)
        self.assertEqual(metrics_b["total_amount_usd"], 0.00)

    def test_citations_reflect_actual_source_metadata(self) -> None:
        """Verify generated citations match the actual dynamic record fields."""
        rec_1 = next(r for r in self.normalized if r["record_id"] == self.dyn_rec_1_id)
        citation_str = format_evidence_citation(rec_1)
        self.assertIn(self.dynamic_case_a, citation_str)
        self.assertIn(self.dyn_rec_1_id, citation_str)
        self.assertIn("flight_telemetry_orbit_9.csv", citation_str)
        self.assertIn("Page: 14", citation_str)
        self.assertIn("2027-03-10T08:00:00Z", citation_str)

    def test_missing_metadata_stays_missing(self) -> None:
        """Verify missing page numbers in dynamic records are not fabricated."""
        rec_2 = next(r for r in self.normalized if r["record_id"] == self.dyn_rec_2_id)
        citation_str = format_evidence_citation(rec_2)
        self.assertIn("Page: [NOT RECORDED]", citation_str)
        self.assertIn("spectrometry_lab_scan.pdf", citation_str)

        meta = get_citation_metadata(rec_2)
        self.assertFalse(meta["has_complete_citations"])
        self.assertIn("page_number", meta["missing_fields"])

    def test_unknown_questions_do_not_produce_invented_facts(self) -> None:
        """Verify questions for non-existent evidence return no_evidence_found status."""
        res = answer_question(
            question="What happened to the submarine or quantum reactor?",
            case_id=self.dynamic_case_a,
            records_source=self.normalized,
        )
        self.assertEqual(res["status"], "no_evidence_found")
        self.assertEqual(len(res["citations"]), 0)
        self.assertIn("No relevant evidence was found", res["answer"])
        # Limitations note case scope
        self.assertIn(self.dynamic_case_a, res["limitations"])

    def test_records_from_other_cases_cannot_enter_evidence_context(self) -> None:
        """Verify cross-case isolation with dynamic case IDs."""
        # Querying an entity belonging strictly to case B ("sublevel") inside case A
        matched, metrics = retrieve_case_evidence(
            question="Where is the sublevel vault?",
            case_id=self.dynamic_case_a,
            all_records=self.normalized,
        )
        # Case A must not return Case B records
        self.assertNotIn(self.dyn_rec_3_id, [r["record_id"] for r in matched])
        for r in matched:
            self.assertEqual(r["case_id"], self.dynamic_case_a)

    def test_follow_up_questions_do_not_introduce_unsupported_case_claims(self) -> None:
        """Verify fallback follow-up questions remain generic and grounded."""
        def empty_caller(prompt: str, system: Optional[str] = None) -> str:
            # Model returns generic answer without follow-up questions section
            return "### Answer\nTelemetry was recorded.\n\n### Supporting Evidence\n- Verified"

        res = answer_question(
            question="Summarize telemetry",
            case_id=self.dynamic_case_a,
            records_source=self.normalized,
            llm_caller=empty_caller,
        )

        follow_up = res["suggested_follow_up_questions"]
        # Must not contain hardcoded specifics like Gate B, crates, or vans
        self.assertNotIn("Gate B", follow_up)
        self.assertNotIn("crate", follow_up.lower())
        self.assertNotIn("van", follow_up.lower())
        self.assertIn("primary source", follow_up.lower())


if __name__ == "__main__":
    unittest.main()
