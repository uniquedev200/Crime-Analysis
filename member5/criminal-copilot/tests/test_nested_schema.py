"""
test_nested_schema.py

Comprehensive unit tests verifying the data-driven normalization layer
for nested case structures (ATLAS, Member 3 output, heterogeneous structured records).
Tests requirement 10:
- Uploaded file is accepted.
- Case ID is discovered dynamically.
- Events and structured record groups (CDR, Financial, ANPR, OSINT) are detected.
- Original source references and provenance are preserved.
- Missing fields are handled without fabricated values.
- Searches and citations work on normalized records.
- Records from separate cases cannot be mixed.
- Unsupported structures yield clear warnings rather than failing the entire file.
- Metadata objects (case, source_index, processing) are not treated as evidence.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from src.evidence_search import (
    EvidenceSearchEngine,
    format_evidence_citation,
    get_citation_metadata,
    load_and_normalize_records,
    search_by_case_id,
    search_text,
)
from src.ui_helpers import (
    get_available_cases,
    get_record_types_for_case,
    parse_uploaded_json,
)
from src.validate_data import validate_and_summarize


def create_representative_nested_fixture() -> Dict[str, Any]:
    """Return a representative nested case JSON structure."""
    return {
        "schema_version": "2.0",
        "payload_type": "ATLAS_MEMBER3_OUTPUT",
        "case": {
            "case_id": "CASE-ALPHA-01",
            "fir_number": "SYN-FIR-01/2026",
            "registration_date": "2026-09-01",
            "police_station": "Metro Central",
        },
        "source_index": [
            {
                "source_id": "SRC-001",
                "file_name": "BANK_RECORDS_ALPHA.xlsx",
                "source_type": "bank_transactions",
                "format": "xlsx",
                "row_count": 1,
            },
            {
                "source_id": "SRC-002",
                "file_name": "CALL_LOGS_ALPHA.xlsx",
                "source_type": "cdr",
                "format": "xlsx",
                "row_count": 1,
            },
            {
                "source_id": "SRC-003",
                "file_name": "FIR_DOC_ALPHA.pdf",
                "source_type": "fir",
                "format": "pdf",
                "page_count": 2,
            },
            {
                "source_id": "SRC-004",
                "file_name": "SURVEILLANCE_ALPHA.pdf",
                "source_type": "surveillance",
                "format": "pdf",
                "page_count": 3,
            },
        ],
        "events": [
            {
                "event_id": "EVT-001",
                "event_type": "case_registration",
                "timestamp": "2026-09-01 10:00:00",
                "description": "Initial formal registration of case",
                "source_id": "SRC-003",
            },
            {
                "event_id": "EVT-002",
                "event_type": "surveillance_log",
                "timestamp": "02/09/2026 14:30:00",
                "description": "Suspect vehicle observed near terminal",
                "source_id": "SRC-004",
                "page_number": 2,
            },
        ],
        "structured_records": {
            "cdr_records": [
                {
                    "Record ID": "CDR-REC-01",
                    "Target / A-Party Number": "910000000100",
                    "B Party Number": "910000000200",
                    "Call date": "02/09/2026",
                    "Call Initiation Time (CIT)": "11:15:00",
                    "Call Duration (second)": 45,
                    "_source_id": "SRC-002",
                }
            ],
            "financial_records": [
                {
                    "transaction_id": "TXN-REC-01",
                    "account_number": "ACC-998877",
                    "booking_time_ist": "2026-09-02 09:00:00",
                    "debit_inr": "5000",
                    "credit_inr": "0",
                    "amount_usd": 60.50,
                    "narration": "Suspicious wire transfer",
                    "_source_id": "SRC-001",
                }
            ],
            "anpr_cctv_records": [
                {
                    "record_id": "ANPR-REC-01",
                    "camera_id": "CAM-NORTH-04",
                    "plate_number": "AB01CD2345",
                    "timestamp": "2026-09-02 12:00:00",
                    "document_name": "TRAFFIC_CCTV_ALPHA.csv",
                }
            ],
            "osint_records": [],
        },
        "entity_mentions": [
            {
                "mention_id": "MENT-001",
                "entity_id": "ENT-PER-01",
                "entity_type": "person",
                "raw_value": "Alex Vance",
                "source_id": "SRC-003",
            }
        ],
        "resolved_entities": [
            {
                "entity_id": "ENT-PER-01",
                "entity_type": "person",
                "canonical_value": "Alex Vance",
                "source_refs": ["SRC-003", "SRC-004"],
            }
        ],
        "processing": {
            "mock_backend": True,
            "member_owner": "Member 5 Investigation Copilot",
        },
    }


class TestNestedSchemaCompatibility(unittest.TestCase):
    """Test suite verifying nested case schema normalization and retrieval."""

    def setUp(self) -> None:
        self.fixture = create_representative_nested_fixture()
        self.raw_bytes = json.dumps(self.fixture).encode("utf-8")

    def test_uploaded_file_accepted_and_case_id_discovered(self) -> None:
        """Verify nested file is parsed without errors and case ID discovered dynamically."""
        records, meta, errors, warnings = parse_uploaded_json(self.raw_bytes)
        self.assertEqual(errors, [])
        self.assertTrue(meta["is_fictional_mock"])
        self.assertIsNotNone(meta["case_info"])
        self.assertEqual(meta["case_info"]["case_id"], "CASE-ALPHA-01")

        cases = get_available_cases(records)
        self.assertEqual(cases, ["CASE-ALPHA-01"])

    def test_events_and_structured_groups_detected(self) -> None:
        """Verify events, CDR, financial, ANPR, mentions, and resolved entities are all normalized."""
        records, _, _, _ = parse_uploaded_json(self.raw_bytes)
        # Expected counts:
        # events: 2
        # cdr_records: 1
        # financial_records: 1
        # anpr_cctv_records: 1
        # entity_mentions: 1
        # resolved_entities: 1
        # Total = 7 records
        self.assertEqual(len(records), 7)

        record_ids = {r["record_id"] for r in records}
        self.assertIn("EVT-001", record_ids)
        self.assertIn("EVT-002", record_ids)
        self.assertIn("CDR-REC-01", record_ids)
        self.assertIn("TXN-REC-01", record_ids)
        self.assertIn("ANPR-REC-01", record_ids)
        self.assertIn("MENT-001", record_ids)
        self.assertIn("ENT-PER-01", record_ids)

        types = get_record_types_for_case(records, "CASE-ALPHA-01")
        self.assertIn("case_registration", types)
        self.assertIn("surveillance_log", types)
        self.assertIn("cdr_records", types)
        self.assertIn("financial_records", types)
        self.assertIn("anpr_cctv_records", types)
        self.assertIn("entity_mention_person", types)
        self.assertIn("resolved_entity_person", types)

    def test_original_source_references_and_provenance_preserved(self) -> None:
        """Verify source_index maps source_id to document_name while keeping original keys."""
        records = load_and_normalize_records(self.fixture)

        # Check financial record provenance mapped from SRC-001
        txn_rec = next(r for r in records if r["record_id"] == "TXN-REC-01")
        self.assertEqual(txn_rec["document_name"], "BANK_RECORDS_ALPHA.xlsx")
        self.assertEqual(txn_rec["_source_id"], "SRC-001")
        self.assertEqual(txn_rec["narration"], "Suspicious wire transfer")
        self.assertEqual(txn_rec["debit_inr"], "5000")

        # Check CDR record provenance mapped from SRC-002
        cdr_rec = next(r for r in records if r["record_id"] == "CDR-REC-01")
        self.assertEqual(cdr_rec["document_name"], "CALL_LOGS_ALPHA.xlsx")
        self.assertEqual(cdr_rec["_source_id"], "SRC-002")
        self.assertEqual(cdr_rec["Target / A-Party Number"], "910000000100")
        self.assertIn("02/09/2026 11:15:00", cdr_rec["timestamp"])

        # Check resolved entity multi-source provenance
        ent_rec = next(r for r in records if r["record_id"] == "ENT-PER-01")
        self.assertIn("FIR_DOC_ALPHA.pdf", ent_rec["document_name"])
        self.assertIn("SURVEILLANCE_ALPHA.pdf", ent_rec["document_name"])
        self.assertEqual(ent_rec["source_refs"], ["SRC-003", "SRC-004"])

    def test_missing_fields_not_fabricated(self) -> None:
        """Verify unrecorded page numbers or timestamps display [NOT RECORDED] rather than invented values."""
        records = load_and_normalize_records(self.fixture)

        # EVT-001 has no page_number
        evt_1 = next(r for r in records if r["record_id"] == "EVT-001")
        self.assertIsNone(evt_1["page_number"])
        meta = get_citation_metadata(evt_1)
        self.assertIsNone(meta["page_number"])
        self.assertIn("page_number", meta["missing_fields"])
        citation_str = format_evidence_citation(evt_1)
        self.assertIn("Page: [NOT RECORDED]", citation_str)
        self.assertIn("Doc: FIR_DOC_ALPHA.pdf", citation_str)

        # EVT-002 has explicit page_number: 2
        evt_2 = next(r for r in records if r["record_id"] == "EVT-002")
        self.assertEqual(evt_2["page_number"], 2)
        citation_2 = format_evidence_citation(evt_2)
        self.assertIn("Page: 2", citation_2)

    def test_searches_and_citations_work_on_normalized_records(self) -> None:
        """Verify EvidenceSearchEngine functions seamlessly across heterogeneous records."""
        engine = EvidenceSearchEngine(self.fixture)

        # Text search across fields
        vance_results = engine.search_text("Vance", case_id="CASE-ALPHA-01")
        self.assertGreaterEqual(len(vance_results), 2)  # MENT-001 and ENT-PER-01

        wire_results = engine.search_text("Suspicious wire", case_id="CASE-ALPHA-01")
        self.assertEqual(len(wire_results), 1)
        self.assertEqual(wire_results[0]["record_id"], "TXN-REC-01")

        # Metrics calculation
        metrics = engine.metrics("CASE-ALPHA-01")
        self.assertEqual(metrics["total_records"], 7)
        self.assertEqual(metrics["total_amount_usd"], 60.50)

        # Chronological sort
        sorted_records = engine.sort_chronological("CASE-ALPHA-01")
        dated_ids = [r["record_id"] for r in sorted_records if r.get("timestamp")]
        # Earliest is EVT-001 (2026-09-01 10:00:00), followed by 2026-09-02 records
        self.assertEqual(dated_ids[0], "EVT-001")

    def test_case_isolation_enforced_strictly(self) -> None:
        """Verify cross-case search strictly prevents record leakage."""
        fixture_with_two_cases = create_representative_nested_fixture()
        # Add a record belonging to a different case
        foreign_rec = {
            "record_id": "FOREIGN-REC-99",
            "case_id": "CASE-BETA-02",
            "record_type": "incident",
            "document_name": "other_case.pdf",
            "description": "Sensitive record in unrelated case",
        }
        fixture_with_two_cases["events"].append(foreign_rec)

        records = load_and_normalize_records(fixture_with_two_cases)

        alpha_records = search_by_case_id(records, "CASE-ALPHA-01")
        self.assertTrue(all(r["case_id"] == "CASE-ALPHA-01" for r in alpha_records))
        self.assertNotIn("FOREIGN-REC-99", [r["record_id"] for r in alpha_records])

        # Search query matching foreign description must return 0 results when scoped to ALPHA
        leak_check = search_text(records, query="unrelated case", case_id="CASE-ALPHA-01")
        self.assertEqual(leak_check, [])

    def test_metadata_objects_not_treated_as_evidence(self) -> None:
        """Verify metadata objects (case, source_index, processing) are not treated as evidence records."""
        records = load_and_normalize_records(self.fixture)
        for r in records:
            self.assertNotEqual(r.get("record_type"), "source_index")
            self.assertNotEqual(r.get("record_type"), "processing")
            self.assertNotEqual(r.get("record_type"), "case")
            self.assertNotIn("mock_backend", r.get("record_id", ""))

    def test_unsupported_structures_produce_clear_warnings(self) -> None:
        """Verify malformed nested groups log warnings rather than failing all records."""
        broken_fixture = create_representative_nested_fixture()
        # Corrupt structured_records by making one group a non-list
        broken_fixture["structured_records"]["corrupted_group"] = "invalid_not_a_list"
        # Add non-dict event
        broken_fixture["events"].append("string_instead_of_object")

        records, meta, errors, warnings = parse_uploaded_json(json.dumps(broken_fixture).encode("utf-8"))
        # File should still be accepted
        self.assertEqual(errors, [])
        # Valid records should still be normalized
        self.assertGreater(len(records), 0)
        # Warnings must identify the unsupported structures
        warn_text = " | ".join(warnings)
        self.assertIn("corrupted_group", warn_text)
        self.assertIn("is not a list", warn_text)
        self.assertIn("is not a JSON object", warn_text)


if __name__ == "__main__":
    unittest.main()
