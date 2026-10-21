"""Unit tests for resolution signal extraction and heuristic ranking.

All tests marked with @pytest.mark.gate3.
"""

from __future__ import annotations

import pytest

from atlas.contracts.enums import EntityType, IdentifierTrust, SignalPolarity
from atlas.contracts.records import Origin, QuoteStatus, SourceRef, UnitKind
from atlas.resolve.nameutils import (
    are_names_compatible,
    clean_name,
    get_name_tokens,
    is_initials_compatible,
    name_key,
    name_similarity_scores,
)
from atlas.resolve.signals import (
    RANK_NOTE,
    compute_heuristic_rank,
    compute_signal_fingerprint,
    extract_signals,
    has_new_evidence,
    load_resolver_weights,
)


def _make_source() -> SourceRef:
    return SourceRef(
        doc_id="DOC-test001",
        file_name="fir_a.pdf",
        file_sha256="a" * 64,
        unit_id="DOC-test001:p001",
        unit_kind=UnitKind.PAGE,
        page=1,
        text_origin=Origin.PDF_TEXT,
        quote="Vikram Singh son of Harbans Singh",
        quote_status=QuoteStatus.VERIFIED,
    )


@pytest.mark.gate3
def test_clean_name_and_tokens() -> None:
    assert clean_name("Shri Vikram Singh") == "Vikram Singh"
    assert clean_name("Dr. Rajesh Sharma, MD") == "Rajesh Sharma, MD"
    assert clean_name("") == ""

    tokens = get_name_tokens("Shri Vikram Singh")
    assert tokens == ["Vikram", "Singh"]
    assert get_name_tokens("") == []


@pytest.mark.gate3
def test_name_key_deterministic() -> None:
    k1 = name_key("Vikram Singh")
    name_key("Vikrum Singh")
    k3 = name_key("Shri Vikram Singh")
    assert isinstance(k1, str)
    assert len(k1) > 0
    # Vikram and Shri Vikram Singh should have identical name_key
    assert k1 == k3


@pytest.mark.gate3
def test_initials_compatible() -> None:
    assert is_initials_compatible("V. Singh", "Vikram Singh") is True
    assert is_initials_compatible("R. K. Sharma", "Rajesh Kumar Sharma") is True
    assert is_initials_compatible("A. Verma", "Vikram Singh") is False
    assert is_initials_compatible("", "Vikram Singh") is False


@pytest.mark.gate3
def test_name_similarity_scores() -> None:
    scores_exact = name_similarity_scores("Vikram Singh", "Vikram Singh")
    assert scores_exact["token_sort_ratio"] == 1.0
    assert scores_exact["jaro_winkler"] == 1.0
    assert scores_exact["composite"] == 1.0

    scores_variant = name_similarity_scores("Vikram Singh", "Vikrum Singh")
    assert scores_variant["composite"] >= 0.85
    assert are_names_compatible("Vikram Singh", "Vikrum Singh") is True

    scores_diff = name_similarity_scores("Vicky", "Vikram Singh")
    assert scores_diff["composite"] < 0.85
    assert are_names_compatible("Vicky", "Vikram Singh") is False

    empty_scores = name_similarity_scores("", "Vikram Singh")
    assert empty_scores["composite"] == 0.0


@pytest.mark.gate3
def test_signals_exact_identifier_strong_vs_unconfirmed() -> None:
    source = _make_source()
    p1 = {
        "name": "Vikram Singh",
        "identifiers": [
            {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value, "source": source}
        ],
    }
    # Candidate with matching strong phone
    cand_strong = {
        "canonical_name": "Vikram Singh",
        "identifiers": [
            {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value, "source": source}
        ],
    }
    signals = extract_signals(p1, cand_strong)
    exact_id_sigs = [s for s in signals if s.kind == "exact_identifier"]
    assert len(exact_id_sigs) == 1
    assert exact_id_sigs[0].polarity == SignalPolarity.SUPPORTS
    assert "+919876543210" in exact_id_sigs[0].detail

    # Candidate with unconfirmed review_required phone
    cand_unconfirmed = {
        "canonical_name": "Vikram Singh",
        "identifiers": [
            {
                "type": "phone",
                "value": "+919876543210",
                "trust": IdentifierTrust.REVIEW_REQUIRED.value,
                "confirmed_by": None,
            }
        ],
    }
    signals_unconf = extract_signals(p1, cand_unconfirmed)
    assert not any(s.kind == "exact_identifier" for s in signals_unconf)

    # Candidate after confirmation by reviewer
    cand_confirmed = {
        "canonical_name": "Vikram Singh",
        "identifiers": [
            {
                "type": "phone",
                "value": "+919876543210",
                "trust": IdentifierTrust.REVIEW_REQUIRED.value,
                "confirmed_by": "analyst_1",
            }
        ],
    }
    signals_conf = extract_signals(p1, cand_confirmed)
    assert any(s.kind == "exact_identifier" for s in signals_conf)


@pytest.mark.gate3
def test_signals_contradictions() -> None:
    # 1. Incompatible entity type
    p_person = {"type": EntityType.PERSON, "name": "Vikram Singh"}
    cand_org = {"type": EntityType.ORGANIZATION, "name": "Vikram Logistics"}
    sigs_type = extract_signals(p_person, cand_org)
    assert any(s.kind == "incompatible_entity_type" and s.polarity == SignalPolarity.CONTRADICTS for s in sigs_type)

    # 2. DOB conflict
    p_dob = {"name": "Vikram Singh", "dob": "1990-05-15"}
    cand_dob = {"canonical_name": "Vikram Singh", "dob": "1975-11-20"}
    sigs_dob = extract_signals(p_dob, cand_dob)
    assert any(s.kind == "dob_conflict" and s.polarity == SignalPolarity.CONTRADICTS for s in sigs_dob)

    # 3. Age conflict (diff > 2)
    p_age = {"name": "Vikram Singh", "age": 32}
    cand_age = {"canonical_name": "Vikram Singh", "age": 48}
    sigs_age = extract_signals(p_age, cand_age)
    assert any(s.kind == "dob_conflict" and s.polarity == SignalPolarity.CONTRADICTS for s in sigs_age)

    # Compatible age (diff <= 2)
    cand_compat_age = {"canonical_name": "Vikram Singh", "age": 33}
    sigs_compat_age = extract_signals(p_age, cand_compat_age)
    assert any(s.kind == "age_dob_compat" and s.polarity == SignalPolarity.SUPPORTS for s in sigs_compat_age)

    # 4. Parent name conflict vs match
    p_father = {"name": "Vikram Singh", "father_name": "Harbans Singh"}
    cand_father_match = {"canonical_name": "Vikram Singh", "father_name": "Harbans Singh"}
    sigs_father_match = extract_signals(p_father, cand_father_match)
    assert any(s.kind == "parent_name" and s.polarity == SignalPolarity.SUPPORTS for s in sigs_father_match)

    cand_father_diff = {"canonical_name": "Vikram Singh", "father_name": "Mohan Lal"}
    sigs_father_diff = extract_signals(p_father, cand_father_diff)
    assert any(s.kind == "parent_name_conflict" and s.polarity == SignalPolarity.CONTRADICTS for s in sigs_father_diff)


@pytest.mark.gate3
def test_signals_supporting_attributes() -> None:
    p = {
        "name": "Vikram Singh",
        "attributes": {
            "address": "House 45, Gali No 3, Laxmi Nagar, Delhi 110092",
            "father_name": "Harbans Singh",
            "age": 32,
        },
        "aliases": ["Vicky"],
        "co_occurrences": ["ORG:DelhiTrans", "VEHICLE:DL01AB1234"],
    }
    cand = {
        "canonical_name": "Vikrum Singh",
        "attributes": {
            "address": "Flat 4, Gali No 3, Laxmi Nagar, Delhi",
            "father_name": "Harbans Singh",
            "age": 32,
        },
        "co_occurrences": ["ORG:DelhiTrans"],
    }
    signals = extract_signals(p, cand)

    kinds = {s.kind for s in signals}
    assert "name_similarity" in kinds
    assert "parent_name" in kinds
    assert "age_dob_compat" in kinds
    assert "address_overlap" in kinds
    assert "co_occurrence" in kinds


@pytest.mark.gate3
def test_signals_alias_stated() -> None:
    p = {"name": "Vicky"}
    cand = {"canonical_name": "Vikram Singh", "aliases": ["Vicky"]}
    signals = extract_signals(p, cand)
    assert any(s.kind == "alias_stated" and s.polarity == SignalPolarity.SUPPORTS for s in signals)


@pytest.mark.gate3
def test_heuristic_rank_bounds_and_determinism() -> None:
    weights = load_resolver_weights()
    assert weights["exact_identifier"] == 1.0
    assert weights["name_similarity"] == 0.4
    assert weights["MIN_RANK"] == 0.3
    assert RANK_NOTE == "heuristic ordering, not a probability"

    # Perfect match signals
    p = {
        "name": "Vikram Singh",
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value}],
        "father_name": "Harbans Singh",
        "age": 32,
    }
    cand = {
        "canonical_name": "Vikram Singh",
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value}],
        "father_name": "Harbans Singh",
        "age": 32,
    }
    signals = extract_signals(p, cand)
    rank1 = compute_heuristic_rank(signals, weights)
    rank2 = compute_heuristic_rank(signals, weights)
    assert rank1 == rank2
    assert 0.0 <= rank1 <= 1.0
    assert rank1 >= 0.8  # Strong match

    # Match with contradictions should be penalized
    cand_conflict = {
        "canonical_name": "Vikram Singh",
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value}],
        "father_name": "Mohan Lal",
        "age": 55,
    }
    signals_conflict = extract_signals(p, cand_conflict)
    rank_conflict = compute_heuristic_rank(signals_conflict, weights)
    assert 0.0 <= rank_conflict <= 1.0
    assert rank_conflict < rank1


@pytest.mark.gate3
def test_fingerprint_and_new_evidence() -> None:
    p = {"name": "Vikram Singh", "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}]}
    cand = {"canonical_name": "Vicky", "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}]}
    sigs1 = extract_signals(p, cand)
    fp1 = compute_signal_fingerprint(sigs1)
    assert isinstance(fp1, str)
    assert len(fp1) == 64

    # Same signals -> no new evidence
    assert has_new_evidence(fp1, sigs1) is False

    # New signal added (e.g. father name added)
    cand_with_father = {**cand, "father_name": "Harbans Singh"}
    p_with_father = {**p, "father_name": "Harbans Singh"}
    sigs2 = extract_signals(p_with_father, cand_with_father)
    assert has_new_evidence(fp1, sigs2) is True
