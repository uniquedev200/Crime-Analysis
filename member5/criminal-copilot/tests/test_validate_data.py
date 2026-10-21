"""
test_validate_data.py

Basic unit tests for src/validate_data.py verifying:
- Exact case, record, and numeric counts on the fictional mock JSON dataset
- Preservation and checking of citation metadata fields
- Prevention of cross-case record mixing and duplicate record IDs
- Protection against exposing personal information (PII) in summaries
- Flexibility for alternative JSON structures
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.validate_data import (
    format_summary_report,
    is_sensitive_field,
    load_and_validate_file,
    validate_and_summarize,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOCK_DATA_PATH = PROJECT_ROOT / "data" / "mock_investigation_data.json"


class TestValidateData(unittest.TestCase):
    """Test suite for the investigation JSON validator and privacy-safe summarizer."""

    def test_mock_dataset_validates_and_counts_accurately(self) -> None:
        """Verify exact counts, totals, and citation coverage on the mock dataset."""
        summary = load_and_validate_file(MOCK_DATA_PATH)

        self.assertTrue(summary["is_valid"], f"Unexpected errors: {summary['errors']}")
        self.assertTrue(summary["is_fictional_mock"])
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["case_ids"], ["CASE-MOCK-001", "CASE-MOCK-002"])
        self.assertEqual(summary["total_records"], 5)
        self.assertEqual(
            summary["records_per_case"],
            {"CASE-MOCK-001": 3, "CASE-MOCK-002": 2},
        )
        # Verify exact Python arithmetic per case without cross-case mixing
        self.assertAlmostEqual(summary["amount_totals_by_case"]["CASE-MOCK-001"], 5750.50)
        self.assertAlmostEqual(summary["amount_totals_by_case"]["CASE-MOCK-002"], 0.00)

        # Verify citation field coverage (REC-103 intentionally has page_number: null)
        coverage = summary["citation_field_coverage"]
        self.assertEqual(coverage["record_id"], 5)
        self.assertEqual(coverage["document_name"], 5)
        self.assertEqual(coverage["page_number"], 4)
        self.assertEqual(coverage["timestamp"], 5)
        self.assertTrue(
            any("REC-103" in w and "page_number" in w for w in summary["warnings"])
        )

    def test_summary_report_does_not_expose_personal_information(self) -> None:
        """Ensure PII values (names, phones, emails, addresses, narratives) never leak."""
        summary = load_and_validate_file(MOCK_DATA_PATH)
        report_text = format_summary_report(summary)
        serialized_summary = json.dumps(summary)

        sensitive_mock_values = [
            "Jordan Vance",
            "Rowan Sterling",
            "Casey Thorne",
            "Morgan Ellis",
            "Avery Quinn",
            "555-0199-MOCK",
            "555-0144-MOCK",
            "r.sterling.mock@example.invalid",
            "a.quinn.mock@example.invalid",
            "742 Evergreen Mock Lane",
            "Synthetic Pier 4 Warehouse",
        ]

        for secret in sensitive_mock_values:
            self.assertNotIn(secret, report_text)
            self.assertNotIn(secret, serialized_summary)

        # Verify document_name is kept as a safe citation field while person_name is flagged
        self.assertFalse(is_sensitive_field("document_name"))
        self.assertTrue(is_sensitive_field("person_name"))
        self.assertTrue(is_sensitive_field("witness_name"))
        self.assertTrue(is_sensitive_field("contact_phone"))

    def test_detects_cross_case_mixing_and_duplicate_record_ids(self) -> None:
        """Ensure validator flags records with mismatched case_id or duplicate record_id."""
        bad_payload = {
            "cases": [
                {
                    "case_id": "CASE-001",
                    "records": [
                        {
                            "record_id": "REC-1",
                            "case_id": "CASE-001",
                            "document_name": "doc1.pdf",
                            "page_number": 1,
                            "timestamp": "2026-10-01T00:00:00Z",
                        },
                        {
                            "record_id": "REC-1",  # Duplicate ID
                            "case_id": "CASE-999",  # Cross-case mismatch
                            "document_name": "doc2.pdf",
                            "page_number": 2,
                            "timestamp": "2026-10-02T00:00:00Z",
                        },
                    ],
                }
            ]
        }

        summary = validate_and_summarize(bad_payload)
        self.assertFalse(summary["is_valid"])
        error_text = " | ".join(summary["errors"])
        self.assertIn("Cross-case mismatch", error_text)
        self.assertIn("Duplicate 'record_id'", error_text)

    def test_supports_alternative_flat_record_list_schema(self) -> None:
        """Ensure validator works if the final team JSON schema is a flat list of records."""
        flat_schema_data = [
            {
                "record_id": "FLAT-01",
                "case_id": "CASE-FLAT-A",
                "record_type": "note",
                "document_name": "memo.pdf",
                "page_number": 1,
                "timestamp": "2026-10-10T12:00:00Z",
                "person_name": "Fictional Individual",
            },
            {
                "record_id": "FLAT-02",
                "case_id": "CASE-FLAT-B",
                "record_type": "note",
                "document_name": "memo2.pdf",
                "page_number": 3,
                "timestamp": "2026-10-11T12:00:00Z",
            },
        ]

        summary = validate_and_summarize(flat_schema_data)
        self.assertTrue(summary["is_valid"])
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["total_records"], 2)
        self.assertIn("person_name", summary["redacted_sensitive_fields"])

    def test_missing_or_invalid_json_file_handled_gracefully(self) -> None:
        """Ensure missing files or broken JSON syntax return structured errors instead of crashing."""
        missing_summary = load_and_validate_file(PROJECT_ROOT / "data" / "does_not_exist.json")
        self.assertFalse(missing_summary["is_valid"])
        self.assertTrue(any("File not found" in err for err in missing_summary["errors"]))

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp.write("{ invalid json ")
            tmp_path = Path(tmp.name)

        try:
            broken_summary = load_and_validate_file(tmp_path)
            self.assertFalse(broken_summary["is_valid"])
            self.assertTrue(any("Invalid JSON syntax" in err for err in broken_summary["errors"]))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


    def test_grouped_warnings_for_missing_metadata(self) -> None:
        """Verify that missing metadata across many records is grouped into concise case-level warnings."""
        many_records = [
            {
                "record_id": f"REC-{i:03d}",
                "case_id": "CASE-SPAM-TEST",
                "record_type": "transaction",
                "document_name": "bulk_txns.csv",
                "page_number": None,
                "timestamp": "2026-10-10T00:00:00Z",
            }
            for i in range(50)
        ]
        summary = validate_and_summarize(many_records)
        self.assertTrue(summary["is_valid"])
        # Should NOT have 50 individual warnings for page_number
        page_warnings = [w for w in summary["warnings"] if "page_number" in w]
        self.assertEqual(len(page_warnings), 1)
        self.assertIn("50 records", page_warnings[0])
        self.assertIn("REC-000", page_warnings[0])
        self.assertIn("CASE-SPAM-TEST", page_warnings[0])


if __name__ == "__main__":
    unittest.main()
