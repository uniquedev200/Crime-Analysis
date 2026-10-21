"""
test_ui_helpers.py

Unit tests for UI helper utilities used by the Streamlit interface.
Verifies case listing, record type extraction, case isolation filtering,
citation card formatting, and dataset disclaimer inspection.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from src.evidence_search import load_and_normalize_records
from src.ui_helpers import (
    extract_metadata_from_dict,
    filter_case_evidence,
    format_citation_card,
    get_available_cases,
    get_record_types_for_case,
    load_dataset_metadata,
    parse_uploaded_json,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOCK_DATA_PATH = PROJECT_ROOT / "data" / "mock_investigation_data.json"


class TestUIHelpers(unittest.TestCase):
    """Test suite for UI helper functions."""

    def setUp(self) -> None:
        self.records = load_and_normalize_records(MOCK_DATA_PATH)

    def test_get_available_cases(self) -> None:
        """Verify unique case IDs are extracted properly."""
        cases = get_available_cases(self.records)
        self.assertEqual(cases, ["CASE-MOCK-001", "CASE-MOCK-002"])

    def test_get_record_types_for_case(self) -> None:
        """Verify distinct record types for a case include 'All Types'."""
        types_001 = get_record_types_for_case(self.records, "CASE-MOCK-001")
        self.assertIn("All Types", types_001)
        self.assertIn("incident_report", types_001)
        self.assertIn("financial_log", types_001)
        self.assertIn("witness_statement", types_001)
        self.assertNotIn("access_log", types_001)  # access_log is in CASE-MOCK-002

    def test_filter_case_evidence_isolation(self) -> None:
        """Verify filtering strictly enforces case isolation."""
        # Query matching CASE-MOCK-002 only should return empty when scoped to CASE-MOCK-001
        res = filter_case_evidence(
            self.records, case_id="CASE-MOCK-001", query="curator", selected_type="All Types"
        )
        self.assertEqual(len(res), 0)

        # Filtering by type within case
        res_type = filter_case_evidence(
            self.records, case_id="CASE-MOCK-001", selected_type="incident_report"
        )
        self.assertEqual(len(res_type), 1)
        self.assertEqual(res_type[0]["record_id"], "REC-101")

        # Empty case_id returns empty list
        self.assertEqual(filter_case_evidence(self.records, case_id=""), [])

    def test_format_citation_card_preserves_and_identifies_missing(self) -> None:
        """Verify citation card displays exact coordinates and flags missing metadata."""
        rec_101 = next(r for r in self.records if r["record_id"] == "REC-101")
        card_101 = format_citation_card(rec_101)
        self.assertEqual(card_101["page_number"], "2")
        self.assertEqual(card_101["document_name"], "mock_pier_incident_report.pdf")
        self.assertEqual(card_101["amount_usd"], "$4,500.00")
        self.assertTrue(card_101["has_complete_citations"])

        # REC-103 lacks page_number
        rec_103 = next(r for r in self.records if r["record_id"] == "REC-103")
        card_103 = format_citation_card(rec_103)
        self.assertEqual(card_103["page_number"], "[NOT RECORDED]")
        self.assertFalse(card_103["has_complete_citations"])

    def test_load_dataset_metadata(self) -> None:
        """Verify detection of fictional mock dataset disclaimer and metadata."""
        meta = load_dataset_metadata(MOCK_DATA_PATH)
        self.assertTrue(meta["is_fictional_mock"])
        self.assertIsNotNone(meta["disclaimer"])
        self.assertIn("FICTIONAL MOCK DATASET", meta["disclaimer"])

    def test_parse_uploaded_json_valid_cases_format(self) -> None:
        """Verify uploading valid JSON with cases structure returns normalized records."""
        payload = b"""{
            "is_fictional_mock": true,
            "_disclaimer": "Test disclaimer",
            "cases": [
                {
                    "case_id": "CASE-TEST-001",
                    "records": [
                        {
                            "record_id": "REC-T01",
                            "record_type": "incident_report",
                            "document_name": "incident.pdf",
                            "page_number": 1,
                            "timestamp": "2024-03-01T10:00:00Z",
                            "summary": "Test incident description."
                        }
                    ]
                }
            ]
        }"""
        records, meta, errors, warnings = parse_uploaded_json(payload)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_id"], "REC-T01")
        self.assertEqual(records[0]["case_id"], "CASE-TEST-001")
        self.assertTrue(meta["is_fictional_mock"])
        self.assertEqual(meta["disclaimer"], "Test disclaimer")

    def test_parse_uploaded_json_valid_flat_records(self) -> None:
        """Verify uploading valid flat list of records."""
        payload = """[
            {
                "record_id": "REC-FLAT-1",
                "case_id": "CASE-FLAT-A",
                "record_type": "financial_log",
                "document_name": "bank.pdf",
                "page_number": 5,
                "amount_usd": 1500.50
            }
        ]"""
        records, meta, errors, warnings = parse_uploaded_json(payload)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_id"], "REC-FLAT-1")
        self.assertEqual(records[0]["case_id"], "CASE-FLAT-A")
        self.assertFalse(meta["is_fictional_mock"])

    def test_parse_uploaded_json_malformed_syntax(self) -> None:
        """Verify malformed JSON syntax produces a clear error and no crash."""
        payload = b'{"cases": [broken json here'
        records, meta, errors, warnings = parse_uploaded_json(payload)
        self.assertEqual(len(records), 0)
        self.assertTrue(any("Invalid JSON syntax" in err for err in errors))

    def test_parse_uploaded_json_empty_payload(self) -> None:
        """Verify empty file produces a clear error."""
        records, meta, errors, warnings = parse_uploaded_json(b"   ")
        self.assertEqual(len(records), 0)
        self.assertTrue(any("Uploaded file is empty" in err for err in errors))

    def test_parse_uploaded_json_invalid_encoding(self) -> None:
        """Verify invalid UTF-8 bytes return an encoding error."""
        bad_bytes = b"\x80\x81\x82"
        records, meta, errors, warnings = parse_uploaded_json(bad_bytes)
        self.assertEqual(len(records), 0)
        self.assertTrue(any("Encoding error" in err for err in errors))

    def test_extract_metadata_from_dict(self) -> None:
        """Verify metadata extraction handles dicts and non-dicts."""
        dict_meta = extract_metadata_from_dict({"is_fictional_mock": True, "_disclaimer": "Fictional"})
        self.assertTrue(dict_meta["is_fictional_mock"])
        self.assertEqual(dict_meta["disclaimer"], "Fictional")

        list_meta = extract_metadata_from_dict([{"record_id": "1"}])
        self.assertFalse(list_meta["is_fictional_mock"])
        self.assertIsNone(list_meta["disclaimer"])


if __name__ == "__main__":
    unittest.main()

