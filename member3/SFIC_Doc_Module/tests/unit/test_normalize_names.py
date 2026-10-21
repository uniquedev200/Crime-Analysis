"""Unit tests for name normalization and key generation.

Covers name_key algorithm, honorific stripping, patronymic parsing,
mixed-script preservation, and negative matching assertions.
All tests are marked gate1.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from atlas.normalize.names import (
    is_valid_person_name,
    name_key,
    parse_patronymic,
    strip_honorifics,
)


@pytest.mark.gate1
class TestNameKey:
    """Tests for name_key generation, phonetic variant collapsing, and initials handling."""

    def test_vikram_variants_produce_same_key(self) -> None:
        variants = ["Vikram", "Vikrum", "Vikrma", "Vikrama"]
        keys = [name_key(v) for v in variants]
        first_key = keys[0]
        for v, k in zip(variants, keys, strict=True):
            assert k == first_key, f"Variant '{v}' gave '{k}' instead of '{first_key}'"
        assert first_key == "vikrm"

    def test_shri_v_singh_and_initials(self) -> None:
        key_shri = name_key("Shri V. Singh")
        assert "shri" not in key_shri
        assert key_shri == "sing v"

        # Reversed order: "Singh, V." should produce same key
        key_reversed = name_key("Singh, V.")
        assert key_reversed == key_shri

    def test_multiple_initials_deterministically_sorted(self) -> None:
        # V. K. Singh vs Singh V. K. vs K. V. Singh
        k1 = name_key("V. K. Singh")
        k2 = name_key("Singh V. K.")
        k3 = name_key("K. V. Singh")
        assert k1 == "sing k v"
        assert k2 == "sing k v"
        assert k3 == "sing k v"

    def test_consonant_variants(self) -> None:
        # w -> v
        assert name_key("Shweta") == name_key("Shveta")
        # ph -> f
        assert name_key("Joseph") == name_key("Josef")
        assert name_key("Phool") == name_key("Fool")

    def test_repeated_letters_collapsed(self) -> None:
        assert name_key("Mohammed") == name_key("Mohamed")
        assert name_key("Pooja") == name_key("Poja")

    def test_negative_vikram_vs_vikas(self) -> None:
        k_vikram = name_key("Vikram")
        k_vikas = name_key("Vikas")
        assert k_vikram != k_vikas, f"Expected different keys but got {k_vikram} vs {k_vikas}"

    def test_negative_arun_vs_varun(self) -> None:
        k_arun = name_key("Arun")
        k_varun = name_key("Varun")
        assert k_arun != k_varun, f"Expected different keys but got {k_arun} vs {k_varun}"

    def test_mixed_script_preserved(self) -> None:
        # Devanagari script preserved
        devanagari_name = "विक्रम"
        k_dev = name_key(devanagari_name)
        assert "विक्रम" in k_dev

        # Mixed Devanagari + Latin
        mixed = "विक्रम Singh"
        k_mixed = name_key(mixed)
        assert "विक्रम" in k_mixed
        assert "sing" in k_mixed

        # Tamil script preserved
        tamil = "சுரேஷ்"
        k_tamil = name_key(tamil)
        assert "சுரேஷ்" in k_tamil

    def test_empty_or_whitespace_name(self) -> None:
        assert name_key("") == ""
        assert name_key("   ") == ""

    def test_original_never_mutated(self) -> None:
        raw = "Shri Vikram Singh"
        raw_copy = copy.copy(raw)
        _ = name_key(raw)
        assert raw == raw_copy

    @settings(max_examples=50)
    @given(
        st.sampled_from(
            [
                "Vikram",
                "Shri V. Singh",
                "Arun",
                "Varun",
                "Sunita Devi",
                "Dr. Rajesh Kumar",
                "विक्रम Singh",
            ]
        )
    )
    def test_name_key_idempotency_hypothesis(self, name: str) -> None:
        k1 = name_key(name)
        k2 = name_key(k1)
        assert k2 == k1, f"Idempotency failed: {k1!r} -> {k2!r}"


@pytest.mark.gate1
class TestStripHonorifics:
    """Tests for honorific title stripping."""

    def test_common_honorifics(self) -> None:
        cases = [
            ("Shri V. Singh", "V. Singh"),
            ("Dr. Rajesh Kumar", "Rajesh Kumar"),
            ("Smt. Sunita Devi", "Sunita Devi"),
            ("Mr. Amit Sharma", "Amit Sharma"),
            ("Mrs. Priya Verma", "Priya Verma"),
            ("Ms. Ananya Roy", "Ananya Roy"),
            ("Sri Ram", "Ram"),
            ("Late Shri Ramesh Chand", "Ramesh Chand"),
        ]
        for raw, expected in cases:
            stripped = strip_honorifics(raw)
            assert stripped == expected, f"Failed for {raw}"

    def test_preserves_internal_name_characters(self) -> None:
        # Names that start with or contain letters matching honorifics (Sridhar, Mridula)
        assert strip_honorifics("Sridhar") == "Sridhar"
        assert strip_honorifics("Mridula") == "Mridula"
        assert strip_honorifics("Dr. Sridhar") == "Sridhar"


@pytest.mark.gate1
class TestParsePatronymic:
    """Tests for patronymic / relative relation parsing."""

    def test_son_of_patterns(self) -> None:
        cases = [
            ("Vikram Singh S/o Ramesh Singh", "Vikram Singh", "Ramesh Singh"),
            ("Vikram Singh s/o Ramesh Singh", "Vikram Singh", "Ramesh Singh"),
            ("Vikram Singh S.O. Ramesh Singh", "Vikram Singh", "Ramesh Singh"),
            ("Vikram Singh, son of Ramesh Singh", "Vikram Singh", "Ramesh Singh"),
        ]
        for text, primary_exp, relative_exp in cases:
            primary, rel = parse_patronymic(text)
            assert primary == primary_exp, f"Primary mismatch for {text}"
            assert rel == relative_exp, f"Relative mismatch for {text}"

    def test_daughter_of_and_wife_of(self) -> None:
        p1, r1 = parse_patronymic("Pooja D/o Suresh Sharma")
        assert p1 == "Pooja"
        assert r1 == "Suresh Sharma"

        p2, r2 = parse_patronymic("Sunita Devi W/o Rajesh Kumar")
        assert p2 == "Sunita Devi"
        assert r2 == "Rajesh Kumar"

    def test_explicit_father_patterns(self) -> None:
        p1, r1 = parse_patronymic("Rajesh Kumar father: Mohan Lal")
        assert p1 == "Rajesh Kumar"
        assert r1 == "Mohan Lal"

        p2, r2 = parse_patronymic("Mohan Lal, father name - Sohan Lal")
        assert p2 == "Mohan Lal"
        assert r2 == "Sohan Lal"

    def test_no_patronymic(self) -> None:
        p, r = parse_patronymic("Vikram Singh")
        assert p == "Vikram Singh"
        assert r is None

        p_empty, r_empty = parse_patronymic("")
        assert p_empty == ""
        assert r_empty is None


@pytest.mark.gate1
class TestIsValidPersonName:
    """Tests for validating genuine personal names vs generic placeholders and narrations."""

    @pytest.mark.parametrize(
        "valid_name",
        [
            "Vikram Singh",
            "Dr. Rajesh Kumar",
            "Smt. Sunita Devi",
            "Pooja Sharma",
            "Ram",
            "John Doe",
            "Mohammad Ali",
            "विक्रम सिंह",
            "Arjun Verma S/o Suresh Verma",
        ],
    )
    def test_valid_person_names(self, valid_name: str) -> None:
        assert is_valid_person_name(valid_name) is True

    @pytest.mark.parametrize(
        "invalid_name",
        [
            # Generic placeholders
            "The Person",
            "person",
            "a person",
            "Unknown Person",
            "unidentified person",
            "unidentified male",
            "Dead body",
            "said person",
            "Individual",
            # Legal / police roles
            "Accused",
            "The accused",
            "Suspect",
            "Complainant",
            "Witness",
            "Investigating Officer",
            "Police",
            "The driver",
            # Banking narrations & noise
            "Service Reversal",
            "Ordinary c.",
            "Ordinary course",
            "Bank charges",
            "Cash deposit",
            "Cash withdrawal",
            "NEFT Reversal",
            # Short / empty / symbols
            "",
            "   ",
            "A",
            "...",
            "12345",
            "N/A",
            "None",
            "null",
        ],
    )
    def test_invalid_person_names(self, invalid_name: str) -> None:
        assert is_valid_person_name(invalid_name) is False
