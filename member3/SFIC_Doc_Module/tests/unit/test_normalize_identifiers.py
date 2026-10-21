"""Unit tests for identifier normalization and validation.

Covers phone numbers, IMEI numbers with Luhn check, Indian vehicle plates,
bank account numbers, and composite text candidate detection.
All tests are marked gate1.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.normalize.identifiers import (
    detect_identifiers,
    normalize_account,
    normalize_phone,
    normalize_vehicle,
    validate_imei,
)


@pytest.mark.gate1
class TestPhoneNormalization:
    """Phone normalization tests for Indian and international numbers."""

    def test_indian_mobile_standard(self) -> None:
        raw = "9876543210"
        norm, status = normalize_phone(raw)
        assert status == "ok"
        assert norm == "+919876543210"

    def test_indian_mobile_plus91_variants(self) -> None:
        variants = [
            "+91 98765 43210",
            "+91-9876543210",
            "+919876543210",
            "+91-98765-43210",
        ]
        for v in variants:
            norm, status = normalize_phone(v)
            assert status == "ok", f"Failed for {v}"
            assert norm == "+919876543210", f"Mismatch for {v}"

    def test_indian_mobile_leading_zero(self) -> None:
        raw = "09876543210"
        norm, status = normalize_phone(raw)
        assert status == "ok"
        assert norm == "+919876543210"

    def test_indian_landline(self) -> None:
        # Delhi STD 011
        norm, status = normalize_phone("01123456789")
        assert status == "ok"
        assert norm == "+911123456789"

        # Mumbai STD 022
        norm, status = normalize_phone("+91-22-22001122")
        assert status == "ok"
        assert norm == "+912222001122"

    def test_international_phone(self) -> None:
        # US number
        norm, status = normalize_phone("+1 415 555 2671")
        assert status == "ok"
        assert norm == "+14155552671"

        # UK number
        norm, status = normalize_phone("+44 20 7946 0991")
        assert status == "ok"
        assert norm == "+442079460991"

    def test_masked_phone(self) -> None:
        masked_cases = ["98XXXXX123", "98765*****", "XXXXX12345", "+91-98XXX-12345"]
        for m in masked_cases:
            norm, status = normalize_phone(m)
            assert status == "masked", f"Expected masked for {m}"
            assert norm is None

    def test_phone_too_short_or_long(self) -> None:
        short_cases = ["12345", "98765", "01123"]
        for s in short_cases:
            norm, status = normalize_phone(s)
            assert status == "invalid", f"Expected invalid for short phone {s}"
            assert norm is None

        long_cases = ["9876543210123456", "+919876543210999999"]
        for long_num in long_cases:
            norm, status = normalize_phone(long_num)
            assert status == "invalid", f"Expected invalid for long phone {long_num}"
            assert norm is None

    def test_phone_empty_or_whitespace(self) -> None:
        for empty in ["", "   ", "\t\n"]:
            norm, status = normalize_phone(empty)
            assert status == "not_applicable"
            assert norm is None

    def test_original_never_mutated(self) -> None:
        raw = "+91 98765 43210"
        raw_copy = copy.copy(raw)
        norm, status = normalize_phone(raw)
        assert status == "ok"
        assert norm == "+919876543210"
        assert raw == raw_copy
        assert raw == "+91 98765 43210"

    @settings(max_examples=50)
    @given(st.sampled_from(["9876543210", "9123456789", "8888899999", "7000012345"]))
    def test_phone_idempotency_hypothesis(self, raw: str) -> None:
        norm1, status1 = normalize_phone(raw)
        assert status1 == "ok"
        assert norm1 is not None
        norm2, status2 = normalize_phone(norm1)
        assert status2 == "ok"
        assert norm2 == norm1


@pytest.mark.gate1
class TestImeiValidation:
    """IMEI validation tests with Luhn check."""

    def test_valid_imei_luhn_pass(self) -> None:
        valid_imeis = [
            "490154203237518",
            "356938035643809",
            "35 693803 564380 9",
            "35-6938-0356-4380-9",
        ]
        for imei in valid_imeis:
            cleaned, status = validate_imei(imei)
            assert status == "ok", f"Expected ok for valid IMEI {imei}"
            assert cleaned is not None
            assert len(cleaned) == 15
            assert cleaned.isdigit()

    def test_invalid_imei_luhn_fail(self) -> None:
        # Last digit altered from valid 490154203237518
        invalid_imeis = [
            "490154203237519",
            "490154203237510",
            "123456789012345",
            "000000000000001",
        ]
        for imei in invalid_imeis:
            cleaned, status = validate_imei(imei)
            assert status == "invalid", f"Expected invalid for {imei}"
            assert cleaned is None

    def test_imei_length_not_15(self) -> None:
        # 14 digits
        cleaned, status = validate_imei("49015420323751")
        assert status == "invalid"
        assert cleaned is None

        # 16 digits
        cleaned, status = validate_imei("4901542032375180")
        assert status == "invalid"
        assert cleaned is None

    def test_imei_masked(self) -> None:
        masked = "356938XXXXX3809"
        cleaned, status = validate_imei(masked)
        assert status == "masked"
        assert cleaned is None

    def test_imei_empty(self) -> None:
        cleaned, status = validate_imei("")
        assert status == "not_applicable"
        assert cleaned is None

    def test_imei_original_never_mutated(self) -> None:
        raw = "35-6938-0356-4380-9"
        raw_copy = copy.copy(raw)
        cleaned, status = validate_imei(raw)
        assert status == "ok"
        assert cleaned == "356938035643809"
        assert raw == raw_copy

    @settings(max_examples=30)
    @given(st.sampled_from(["490154203237518", "356938035643809"]))
    def test_imei_idempotency_hypothesis(self, imei: str) -> None:
        cleaned1, status1 = validate_imei(imei)
        assert status1 == "ok"
        assert cleaned1 is not None
        cleaned2, status2 = validate_imei(cleaned1)
        assert status2 == "ok"
        assert cleaned2 == cleaned1


@pytest.mark.gate1
class TestVehicleNormalization:
    """Vehicle registration plate tests: standard, BH-series, leading zeros."""

    def test_standard_vehicle_plates(self) -> None:
        valid_plates = [
            ("MH12AB1234", "MH12AB1234"),
            ("mh-12-ab-1234", "MH12AB1234"),
            ("DL 01 A 0001", "DL01A0001"),
            ("KA-05-NB-9999", "KA05NB9999"),
            ("UP32AA1111", "UP32AA1111"),
            ("DL1C1234", "DL1C1234"),
            ("CH011234", "CH011234"),
        ]
        for raw, expected in valid_plates:
            norm, status = normalize_vehicle(raw)
            assert status == "ok", f"Expected ok for {raw}"
            assert norm == expected, f"Mismatch for {raw}"

    def test_vehicle_leading_zeros_preserved(self) -> None:
        plates_with_zeros = [
            ("DL 01 A 0001", "DL01A0001"),
            ("MH 02 AA 0005", "MH02AA0005"),
            ("KA 04 E 0010", "KA04E0010"),
        ]
        for raw, expected in plates_with_zeros:
            norm, status = normalize_vehicle(raw)
            assert status == "ok"
            assert norm == expected
            # Specifically check that '0001', '0005', '0010' were not stripped to '1', '5', '10'
            assert expected[-4:] in norm

    def test_bh_series_vehicle_plates(self) -> None:
        bh_plates = [
            ("22BH1234AB", "22BH1234AB"),
            ("21 BH 9999 A", "21BH9999A"),
            ("23-bh-0001-aa", "23BH0001AA"),
        ]
        for raw, expected in bh_plates:
            norm, status = normalize_vehicle(raw)
            assert status == "ok", f"Expected ok for BH plate {raw}"
            assert norm == expected

    def test_vehicle_format_unrecognized(self) -> None:
        unrecognized = [
            "ABC 123",
            "1234 AB",
            "MH-123",
            "INVALID_PLATE",
            "123456789",
        ]
        for odd in unrecognized:
            norm, status = normalize_vehicle(odd)
            assert status == "format_unrecognized", f"Expected format_unrecognized for {odd}"
            assert norm is None

    def test_vehicle_masked(self) -> None:
        masked = "MH12XX1234"
        norm, status = normalize_vehicle(masked)
        assert status == "masked"
        assert norm is None

    def test_vehicle_empty(self) -> None:
        norm, status = normalize_vehicle("")
        assert status == "not_applicable"
        assert norm is None

    def test_vehicle_original_never_mutated(self) -> None:
        raw = "DL 01 A 0001"
        raw_copy = copy.copy(raw)
        norm, status = normalize_vehicle(raw)
        assert status == "ok"
        assert norm == "DL01A0001"
        assert raw == raw_copy

    @settings(max_examples=30)
    @given(st.sampled_from(["MH12AB1234", "DL01A0001", "22BH1234AB"]))
    def test_vehicle_idempotency_hypothesis(self, plate: str) -> None:
        norm1, status1 = normalize_vehicle(plate)
        assert status1 == "ok"
        assert norm1 is not None
        norm2, status2 = normalize_vehicle(norm1)
        assert status2 == "ok"
        assert norm2 == norm1


@pytest.mark.gate1
class TestAccountNormalization:
    """Bank account normalization tests (9 to 18 digits, leading zeros preserved)."""

    def test_account_valid_lengths(self) -> None:
        # Min 9 digits
        norm9, status9 = normalize_account("123456789")
        assert status9 == "ok"
        assert norm9 == "123456789"

        # Max 18 digits
        norm18, status18 = normalize_account("123456789012345678")
        assert status18 == "ok"
        assert norm18 == "123456789012345678"

        # Standard 12-digit Indian account
        norm12, status12 = normalize_account("9876 5432 1012")
        assert status12 == "ok"
        assert norm12 == "987654321012"

    def test_account_leading_zeros_preserved(self) -> None:
        raw = "000123456789"
        norm, status = normalize_account(raw)
        assert status == "ok"
        assert norm == "000123456789"
        assert norm.startswith("000")

    def test_account_too_short_or_long(self) -> None:
        # 8 digits (too short)
        norm, status = normalize_account("12345678")
        assert status == "invalid"
        assert norm is None

        # 19 digits (too long)
        norm, status = normalize_account("1234567890123456789")
        assert status == "invalid"
        assert norm is None

    def test_account_non_digits(self) -> None:
        norm, status = normalize_account("12345ABC678")
        assert status == "invalid"
        assert norm is None

    def test_account_masked(self) -> None:
        norm, status = normalize_account("12XXXXXX89")
        assert status == "masked"
        assert norm is None

    def test_account_empty(self) -> None:
        norm, status = normalize_account("")
        assert status == "not_applicable"
        assert norm is None

    def test_account_original_never_mutated(self) -> None:
        raw = "000123456789"
        raw_copy = copy.copy(raw)
        norm, status = normalize_account(raw)
        assert status == "ok"
        assert norm == "000123456789"
        assert raw == raw_copy

    @settings(max_examples=30)
    @given(st.sampled_from(["123456789", "000123456789", "9876543210123456"]))
    def test_account_idempotency_hypothesis(self, acct: str) -> None:
        norm1, status1 = normalize_account(acct)
        assert status1 == "ok"
        assert norm1 is not None
        norm2, status2 = normalize_account(norm1)
        assert status2 == "ok"
        assert norm2 == norm1


@pytest.mark.gate1
class TestDetectIdentifiers:
    """Detection of identifier candidates across free text."""

    def test_detect_all_categories(self) -> None:
        text = (
            "Complainant reported phone +91 98765 43210. "
            "Accused device IMEI: 490154203237518. "
            "Beneficiary A/c No. 000123456789. "
            "Vehicle used was MH-12-AB-1234 and 22BH1234AB. "
            "Masked contact: 98XXXXX123."
        )
        candidates = detect_identifiers(text)
        types = [c["type"] for c in candidates]
        assert "PHONE" in types
        assert "IMEI" in types
        assert "ACCOUNT" in types
        assert "VEHICLE" in types

        # Check vehicle candidate
        veh = [c for c in candidates if c["type"] == "VEHICLE"]
        assert len(veh) >= 2
        assert any(v["normalized_value"] == "MH12AB1234" for v in veh)
        assert any(v["normalized_value"] == "22BH1234AB" for v in veh)

        # Check account candidate
        acct = [c for c in candidates if c["type"] == "ACCOUNT"]
        assert len(acct) >= 1
        assert acct[0]["normalized_value"] == "000123456789"
        assert acct[0]["status"] == "ok"

        # Check IMEI candidate
        imei = [c for c in candidates if c["type"] == "IMEI"]
        assert len(imei) >= 1
        assert imei[0]["normalized_value"] == "490154203237518"
        assert imei[0]["status"] == "ok"

        # Check masked phone candidate
        masked_phones = [c for c in candidates if c["type"] == "PHONE" and c["status"] == "masked"]
        assert len(masked_phones) >= 1
        assert "98XXXXX123" in masked_phones[0]["raw_text"]

    def test_empty_text_returns_empty_list(self) -> None:
        assert detect_identifiers("") == []
        assert detect_identifiers("   ") == []
