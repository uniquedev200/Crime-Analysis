"""Unit tests for date normalization, ambiguity tracking, and timezones.

Covers DD/MM vs MM/DD ambiguity classification, Excel serial dates,
timezone assignment (Asia/Kolkata ONLY when IST/+05:30), profile-directed
parsing, invalid date handling, and hypothesis idempotency.
All tests are marked gate1.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.normalize.dates import normalize_date


@pytest.mark.gate1
class TestDateAmbiguity:
    """Tests for free-text date ambiguity (day <= 12 and month <= 12)."""

    def test_day_and_month_both_lte_12_is_ambiguous(self) -> None:
        ambiguous_cases = [
            "05/06/2023",
            "06/05/2023",
            "01-02-2022",
            "10/11/2023",
            "12/04/2021",
        ]
        for c in ambiguous_cases:
            res = normalize_date(c)
            assert res["ambiguity"] == "dmy_mdy", f"Expected dmy_mdy for {c}"
            assert res["normalized_iso"] is None, f"Expected null normalized_iso for {c}"
            assert res["original_text"] == c

    def test_profile_format_resolves_ambiguity(self) -> None:
        text = "05/06/2023"
        # DMY: 5th June 2023
        res_dmy = normalize_date(text, profile_format="%d/%m/%Y")
        assert res_dmy["ambiguity"] == "none"
        assert res_dmy["normalized_iso"] == "2023-06-05"

        # MDY: 6th May 2023
        res_mdy = normalize_date(text, profile_format="%m/%d/%Y")
        assert res_mdy["ambiguity"] == "none"
        assert res_mdy["normalized_iso"] == "2023-05-06"

    def test_identical_day_and_month_is_unambiguous(self) -> None:
        # 05/05/2023 is May 5 in both DMY and MDY
        res = normalize_date("05/05/2023")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-05-05"


@pytest.mark.gate1
class TestValidDates:
    """Tests for unambiguous valid dates."""

    def test_day_gt_12_is_unambiguous_dmy(self) -> None:
        res = normalize_date("25/05/2023")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-05-25"

    def test_month_gt_12_in_pos2_is_unambiguous_mdy(self) -> None:
        res = normalize_date("05/25/2023")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-05-25"

    def test_iso_format_unambiguous(self) -> None:
        res = normalize_date("2023-05-25")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-05-25"

    def test_named_month_unambiguous(self) -> None:
        res1 = normalize_date("12 May 2023")
        assert res1["ambiguity"] == "none"
        assert res1["normalized_iso"] == "2023-05-12"

        res2 = normalize_date("May 12, 2023")
        assert res2["ambiguity"] == "none"
        assert res2["normalized_iso"] == "2023-05-12"

    def test_date_with_time(self) -> None:
        res = normalize_date("25/05/2023 14:30:00")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-05-25T14:30:00"


@pytest.mark.gate1
class TestExcelSerialDates:
    """Tests for Excel serial date numbers."""

    def test_integer_excel_serial(self) -> None:
        # 44927 is 2023-01-01
        res = normalize_date("44927")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-01-01"

    def test_float_excel_serial_with_time(self) -> None:
        # 44927.5 is 2023-01-01 12:00:00
        res = normalize_date("44927.5")
        assert res["ambiguity"] == "none"
        assert res["normalized_iso"] == "2023-01-01T12:00:00"


@pytest.mark.gate1
class TestTimezones:
    """Tests for timezone handling: Asia/Kolkata ONLY when IST or +05:30 present."""

    def test_ist_present_assigns_kolkata(self) -> None:
        cases = [
            "25/05/2023 14:30:00 IST",
            "25/05/2023 +05:30",
            "2023-05-25 10:00:00 +05:30",
        ]
        for c in cases:
            res = normalize_date(c)
            assert res["timezone"] == "Asia/Kolkata", f"Expected Asia/Kolkata for {c}"

    def test_absence_of_ist_leaves_timezone_null(self) -> None:
        cases = [
            "25/05/2023 14:30:00",
            "25/05/2023",
            "2023-05-25",
            "25/05/2023 14:30:00 UTC",
            "25/05/2023 Z",
        ]
        for c in cases:
            res = normalize_date(c)
            assert res["timezone"] is None, f"Expected null timezone for {c}"


@pytest.mark.gate1
class TestInvalidAndPartialDates:
    """Tests for invalid calendar dates and partial dates."""

    def test_invalid_calendar_dates(self) -> None:
        invalid_cases = [
            "31/02/2023",  # Feb 31 does not exist
            "32/01/2023",  # Day 32
            "2023-02-30",  # Feb 30 does not exist
            "invalid date text",
            "",
            "   ",
        ]
        for inv in invalid_cases:
            res = normalize_date(inv)
            assert res["ambiguity"] == "unparseable", f"Expected unparseable for {inv}"
            assert res["normalized_iso"] is None

    def test_partial_dates(self) -> None:
        res_year = normalize_date("2023")
        assert res_year["ambiguity"] == "partial"
        assert res_year["normalized_iso"] == "2023"

        res_ym = normalize_date("2023-05")
        assert res_ym["ambiguity"] == "partial"
        assert res_ym["normalized_iso"] == "2023-05"


@pytest.mark.gate1
class TestDateDeterminismAndImmutability:
    """Immutability and hypothesis-based idempotency tests for dates."""

    def test_original_text_never_mutated(self) -> None:
        raw = "25/05/2023 14:30:00 IST"
        raw_copy = copy.copy(raw)
        res = normalize_date(raw)
        assert raw == raw_copy
        assert res["original_text"] == raw

    @settings(max_examples=50)
    @given(
        st.sampled_from(
            [
                "25/05/2023",
                "2023-05-25",
                "12 May 2023",
                "44927",
                "2023-01-01",
                "2023-05-25T14:30:00",
            ]
        )
    )
    def test_date_idempotency_hypothesis(self, text: str) -> None:
        res1 = normalize_date(text)
        if res1["normalized_iso"] is not None:
            res2 = normalize_date(res1["normalized_iso"])
            assert res2["normalized_iso"] == res1["normalized_iso"], (
                f"Idempotency failed: {res1['normalized_iso']!r} -> {res2['normalized_iso']!r}"
            )
