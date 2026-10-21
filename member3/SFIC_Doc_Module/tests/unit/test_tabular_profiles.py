"""Gate 1 unit tests for tabular profile detection, date handling, and mapping suggestions.

Marked with @pytest.mark.gate1.
Tests profile loading, header set comparison, unconfirmed header rejection (zero facts),
date ambiguity rules, Excel serial numbers, explicit IST timezone handling, and mapping suggestion generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.contracts.enums import ReviewKind, TimeAmbiguity
from atlas.contracts.ids import make_doc_id
from atlas.contracts.records import ReviewItem
from atlas.tabular.cdr import parse_cdr
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.mapping_suggest import suggest_mapping
from atlas.tabular.profiles import detect_profile, load_profile


@pytest.mark.gate1
def test_load_profile() -> None:
    profiles_dir = Path("profiles")
    cdr_profile = load_profile(profiles_dir / "cdr_v1.yaml")
    assert cdr_profile["name"] == "cdr_v1"
    assert "a_party" in cdr_profile["required_headers"]
    assert "calling_number" in cdr_profile["header_aliases"]

    bank_profile = load_profile(profiles_dir / "bank_v1.yaml")
    assert bank_profile["name"] == "bank_v1"
    assert "txn_id" in bank_profile["required_headers"]
    assert "debit_account" in bank_profile["header_aliases"]


@pytest.mark.gate1
def test_detect_profile_exact_and_aliased() -> None:
    profiles_dir = Path("profiles")

    # Exact CDR headers
    exact_cdr = ["a_party", "b_party", "start_time", "duration_s", "call_type"]
    assert detect_profile(exact_cdr, profiles_dir) == "cdr_v1"

    # Aliased CDR headers
    aliased_cdr = ["Calling Number", "Called Number", "Start Time", "Duration", "Type"]
    assert detect_profile(aliased_cdr, profiles_dir) == "cdr_v1"

    # Exact Bank headers
    exact_bank = ["txn_id", "txn_date", "from_account", "to_account", "amount"]
    assert detect_profile(exact_bank, profiles_dir) == "bank_v1"

    # Aliased Bank headers
    aliased_bank = ["transaction_id", "date", "debit_account", "credit_account", "transaction_amount"]
    assert detect_profile(aliased_bank, profiles_dir) == "bank_v1"


@pytest.mark.gate1
def test_unknown_headers_mapping_unconfirmed_and_zero_facts() -> None:
    profiles_dir = Path("profiles")

    # Headers not recognized by any profile
    unknown_headers = ["customer_name", "department", "salary", "bonus"]
    detected = detect_profile(unknown_headers, profiles_dir)
    assert detected is None

    # Partially recognized but containing unconfirmed unknown header
    mixed_headers = ["a_party", "b_party", "start_time", "duration_s", "call_type", "unrecognized_col_xyz"]
    assert detect_profile(mixed_headers, profiles_dir) is None

    # Test that parse_cdr with None profile returns zero facts and triggers mapping_unconfirmed
    case_id = "CASE_UNKNOWN_001"
    doc_id = make_doc_id("e" * 64)
    dummy_rows = [{"row_num": 2, "a_party": "9876543210", "b_party": "9123456780", "unrecognized_col_xyz": "foo"}]
    review_items: list[ReviewItem] = []

    events, aggregates, mentions = parse_cdr(
        dummy_rows,
        profile=None,
        case_id=case_id,
        doc_id=doc_id,
        review_items=review_items,
    )

    # Invariant: Zero facts parsed when mapping is unconfirmed
    assert len(events) == 0
    assert len(aggregates) == 0
    assert len(mentions) == 0

    # Review item created
    assert len(review_items) == 1
    assert review_items[0].kind == ReviewKind.MAPPING_UNCONFIRMED


@pytest.mark.gate1
def test_date_dd_mm_ambiguity() -> None:
    # 05/06/2023: Both 5 and 6 are <= 12, so day/month order is ambiguous without profile
    ambig_res = parse_date_with_profile("05/06/2023", profile_format=None)
    assert ambig_res["ambiguity"] == TimeAmbiguity.DMY_MDY
    assert ambig_res["normalized_iso"] is None

    # 25/06/2023: 25 > 12, so 25 must be day, 6 must be month -> unambiguous DMY
    unambig_res = parse_date_with_profile("25/06/2023", profile_format=None)
    assert unambig_res["ambiguity"] == TimeAmbiguity.NONE
    assert unambig_res["normalized_iso"] == "2023-06-25T00:00:00"

    # With explicit profile format %d/%m/%Y, 05/06/2023 is resolved unambiguously
    profile_res = parse_date_with_profile("05/06/2023", profile_format="%d/%m/%Y")
    assert profile_res["ambiguity"] == TimeAmbiguity.NONE
    assert profile_res["normalized_iso"] == "2023-06-05T00:00:00"


@pytest.mark.gate1
def test_date_excel_serial() -> None:
    # Excel serial 44927 corresponds to 2023-01-01
    res_int = parse_date_with_profile(44927)
    assert res_int["ambiguity"] == TimeAmbiguity.NONE
    assert "2023-01-01" in (res_int["normalized_iso"] or "")

    # Excel serial 44927.5 corresponds to 2023-01-01 12:00:00
    res_float = parse_date_with_profile(44927.5)
    assert res_float["ambiguity"] == TimeAmbiguity.NONE
    assert "2023-01-01T12:00:00" in (res_float["normalized_iso"] or "")


@pytest.mark.gate1
def test_date_ist_timezone() -> None:
    # IST in text -> Asia/Kolkata
    res_ist = parse_date_with_profile("2023-01-01 10:00:00 IST")
    assert res_ist["timezone"] == "Asia/Kolkata"

    # +05:30 in text -> Asia/Kolkata
    res_offset = parse_date_with_profile("2023-01-01 10:00:00+05:30")
    assert res_offset["timezone"] == "Asia/Kolkata"

    # Profile explicitly declaring IST
    res_prof_tz = parse_date_with_profile("2023-01-01 10:00:00", timezone="Asia/Kolkata")
    assert res_prof_tz["timezone"] == "Asia/Kolkata"

    # No timezone mentioned -> timezone is null (no silent assumptions)
    res_no_tz = parse_date_with_profile("2023-01-01 10:00:00")
    assert res_no_tz["timezone"] is None


@pytest.mark.gate1
def test_date_invalid() -> None:
    res_inv = parse_date_with_profile("invalid-gibberish-date")
    assert res_inv["ambiguity"] == TimeAmbiguity.UNPARSEABLE
    assert res_inv["normalized_iso"] is None

    res_empty = parse_date_with_profile("")
    assert res_empty["ambiguity"] == TimeAmbiguity.UNPARSEABLE

    res_none = parse_date_with_profile(None)
    assert res_none["ambiguity"] == TimeAmbiguity.UNPARSEABLE


@pytest.mark.gate1
def test_suggest_mapping_headers_only(tmp_path: Path) -> None:
    pending_dir = tmp_path / "pending"

    # Class to verify that ONLY headers are received
    class MockLlmClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
            self.calls.append({"system": system, "user": user, "schema": schema})
            # Verify no row values or excessive text in user prompt
            assert "Column headers:" in user
            return {
                "profile_family": "cdr",
                "suggested_profile_name": "cdr_vendor_x",
                "mappings": {
                    "source_num": "a_party",
                    "dest_num": "b_party",
                    "sec": "duration_s",
                },
            }

    mock_llm = MockLlmClient()
    headers = ["source_num", "dest_num", "sec"]

    result = suggest_mapping(headers, llm_client=mock_llm, pending_dir=pending_dir)

    assert len(mock_llm.calls) == 1
    assert result["status"] == "pending_confirmation"
    assert result["requires_confirmation"] is True
    assert Path(result["pending_path"]).exists()

    # Verify written draft YAML
    draft = load_profile(result["pending_path"])
    assert draft["name"] == "cdr_vendor_x"
    assert draft["requires_confirmation"] is True
    assert draft["header_aliases"]["source_num"] == "a_party"


@pytest.mark.gate1
def test_suggest_mapping_rejects_row_data(tmp_path: Path) -> None:
    pending_dir = tmp_path / "pending"
    # Attempting to pass multiline row data or huge values should raise ValueError
    bad_headers = ["header1\n9876543210,9123456780,100", "header2"]
    with pytest.raises(ValueError) as exc_info:
        suggest_mapping(bad_headers, pending_dir=pending_dir)
    assert "row data or multiline text" in str(exc_info.value)
