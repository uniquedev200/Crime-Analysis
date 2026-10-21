"""Unit tests for the Section 5.10 candidate generation and status rules engine.

All tests marked with @pytest.mark.gate3.
"""

from __future__ import annotations

import pytest

from atlas.contracts.enums import EntityType, IdentifierTrust, ReviewActionType, SuggestionStatus
from atlas.resolve.candidates import generate_suggestions
from atlas.resolve.store_sqlite import SqliteEntityStore


@pytest.fixture
def empty_store() -> SqliteEntityStore:
    store = SqliteEntityStore(":memory:")
    yield store
    store.close()


@pytest.mark.gate3
def test_exact_strong_identifier_similar_name_yields_candidate(empty_store: SqliteEntityStore) -> None:
    # Seed Case A candidate: Vikram Singh
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:c1",
            "case_id": "CASE-A-001",
            "cluster_id": "c1",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "name_variants": ["Vikrum Singh"],
            "aliases": ["Vicky"],
            "attributes": {"father_name": "Harbans Singh", "age": 32},
            "mention_ids": ["M-A-1"],
            "identifiers": [
                {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": [],
        }
    )

    # In Case B: Vikrum Singh with same phone
    new_person = {
        "person_id": "PERSON:CASE-B-002:c1",
        "case_id": "CASE-B-002",
        "canonical_name": "Vikrum Singh",
        "identifiers": [
            {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"father_name": "Harbans Singh", "age": 32},
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug.status == SuggestionStatus.CANDIDATE
    assert sug.candidate_entity_id == "PERSON:CASE-A-001:c1"
    assert sug.requires_human_decision is True
    assert sug.rank_note == "heuristic ordering, not a probability"
    assert sug.heuristic_rank is not None and sug.heuristic_rank >= 0.7


@pytest.mark.gate3
def test_vicky_vs_vikram_singh_shared_phone_needs_review(empty_store: SqliteEntityStore) -> None:
    # Case A: Vikram Singh
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:c1",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [
                {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
            ],
            "attributes": {"father_name": "Harbans Singh", "age": 32},
        }
    )

    # Case B: Vicky with same phone (unconfirmed alias situation)
    new_person = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "canonical_name": "Vicky",
        "identifiers": [
            {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
        ],
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug.status == SuggestionStatus.NEEDS_REVIEW
    assert (
        "dissimilar" in sug.explanation.lower()
        or "alias" in sug.explanation.lower()
        or "shared" in sug.explanation.lower()
    )
    assert sug.requires_human_decision is True


@pytest.mark.gate3
def test_family_shared_phone_needs_review_or_ambiguous(empty_store: SqliteEntityStore) -> None:
    # Case A: Pooja Sharma using family phone
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:pooja",
            "case_id": "CASE-A-001",
            "canonical_name": "Pooja Sharma",
            "name_key": "pooja sharma",
            "identifiers": [
                {"type": "phone", "value": "+919844455566", "trust": IdentifierTrust.STRONG.value},
            ],
            "attributes": {"age": 26, "father_name": "Dinesh Sharma"},
        }
    )

    # Case B: Sunita Sharma (mother) using the same family phone
    new_person = {
        "person_id": "PERSON:CASE-B-002:sunita",
        "case_id": "CASE-B-002",
        "canonical_name": "Sunita Sharma",
        "identifiers": [
            {"type": "phone", "value": "+919844455566", "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": 50, "father_name": "Dinesh Sharma"},
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    assert len(suggestions) == 1
    sug = suggestions[0]
    # Dissimilar age (> 2 years difference) creates a contradiction, or dissimilar names
    assert sug.status in (SuggestionStatus.NEEDS_REVIEW, SuggestionStatus.AMBIGUOUS)
    assert sug.requires_human_decision is True


@pytest.mark.gate3
def test_reassigned_number_scenario_not_candidate(empty_store: SqliteEntityStore) -> None:
    # Case A: Old owner of phone, age 25
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:p1",
            "case_id": "CASE-A-001",
            "canonical_name": "Amit Kumar",
            "name_key": "amit kumar",
            "identifiers": [
                {"type": "phone", "value": "+919800011122", "trust": IdentifierTrust.STRONG.value},
            ],
            "attributes": {"age": 25, "dob": "1999-01-01"},
        }
    )

    # Case B: New owner years later, different person and age
    new_person = {
        "person_id": "PERSON:CASE-B-002:p2",
        "case_id": "CASE-B-002",
        "canonical_name": "Suresh Gupta",
        "identifiers": [
            {"type": "phone", "value": "+919800011122", "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": 55, "dob": "1969-05-12"},
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    assert len(suggestions) == 1
    sug = suggestions[0]
    assert sug.status != SuggestionStatus.CANDIDATE
    assert sug.status in (SuggestionStatus.NEEDS_REVIEW, SuggestionStatus.AMBIGUOUS)


@pytest.mark.gate3
def test_two_same_name_people_with_shared_phone_is_ambiguous(empty_store: SqliteEntityStore) -> None:
    # Two people with same name "Vikram Singh" in Case A with identical or close phone/attributes
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:vikram1",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [
                {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
            ],
            "attributes": {"age": 32, "father_name": "Harbans Singh"},
        }
    )
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:vikram2",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [
                {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
            ],
            "attributes": {"age": 33, "father_name": "Harbans Singh"},
        }
    )

    new_person = {
        "person_id": "PERSON:CASE-B-002:new_vikram",
        "case_id": "CASE-B-002",
        "canonical_name": "Vikram Singh",
        "identifiers": [
            {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
        ],
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    assert len(suggestions) >= 2
    # Because ranks are tied or within epsilon, both candidates must be marked AMBIGUOUS
    for sug in suggestions:
        assert sug.status == SuggestionStatus.AMBIGUOUS
        assert "ambiguous" in sug.explanation.lower()


@pytest.mark.gate3
def test_common_name_only_no_suggestion_without_corroboration(empty_store: SqliteEntityStore) -> None:
    # Case A: Rahul Sharma
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:rahul",
            "case_id": "CASE-A-001",
            "canonical_name": "Rahul Sharma",
            "name_key": "rahul sharma",
            "identifiers": [],
            "attributes": {},
        }
    )

    # Case B: Rahul Sharma with no phone, no father, no age, no address
    new_person = {
        "person_id": "PERSON:CASE-B-002:rahul",
        "case_id": "CASE-B-002",
        "canonical_name": "Rahul Sharma",
        "identifiers": [],
        "attributes": {},
    }

    suggestions = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )

    # Rule: Name-only without corroborating signal: no suggestion emitted
    assert len(suggestions) == 0

    # But with corroborating signal (e.g. matching father_name) -> suggestion is emitted
    new_person_corroborated = {
        "person_id": "PERSON:CASE-B-002:rahul",
        "case_id": "CASE-B-002",
        "canonical_name": "Rahul Sharma",
        "identifiers": [],
        "attributes": {"father_name": "Sanjay Sharma"},
    }
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:rahul2",
            "case_id": "CASE-A-001",
            "canonical_name": "Rahul Sharma",
            "name_key": "rahul sharma",
            "identifiers": [],
            "attributes": {"father_name": "Sanjay Sharma"},
        }
    )
    sugs_corrob = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person_corroborated],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs_corrob) == 1
    assert sugs_corrob[0].status == SuggestionStatus.NEEDS_REVIEW


@pytest.mark.gate3
def test_incompatible_entity_types_never_match(empty_store: SqliteEntityStore) -> None:
    empty_store.store_case_person(
        {
            "person_id": "ORG:CASE-A-001:delhi_trans",
            "case_id": "CASE-A-001",
            "canonical_name": "Delhi Transport Corp",
            "name_key": "delhi transport corp",
            "type": EntityType.ORGANIZATION,
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )

    new_person = {
        "person_id": "PERSON:CASE-B-002:p1",
        "case_id": "CASE-B-002",
        "canonical_name": "Vikram Singh",
        "type": EntityType.PERSON,
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
    }

    # Since candidate in store is an organization (mock or different type)
    # Let's ensure candidate has incompatible type in store or extract_signals
    # By updating candidate type
    generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    # Organization vs Person never produces suggestion
    # If store stores case_persons as EntityType.PERSON, let's test with entity type mismatch
    new_org = {
        "person_id": "ORG:CASE-B-002:org1",
        "case_id": "CASE-B-002",
        "canonical_name": "Delhi Transport Corp",
        "type": EntityType.ORGANIZATION,
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
    }
    sugs_incompat = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_org],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    # Candidate in store is PERSON (default), new is ORGANIZATION -> incompatible -> 0 suggestions
    assert len(sugs_incompat) == 0


@pytest.mark.gate3
def test_ocr_unconfirmed_id_excluded_until_confirmed(empty_store: SqliteEntityStore) -> None:
    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:vikram",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [
                {"type": "phone", "value": "+919876543210", "trust": IdentifierTrust.STRONG.value},
            ],
        }
    )

    # In Case B: Person has phone extracted from OCR, marked REVIEW_REQUIRED, confirmed_by is None
    new_person = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "canonical_name": "Vicky",
        "identifiers": [
            {
                "type": "phone",
                "value": "+919876543210",
                "trust": IdentifierTrust.REVIEW_REQUIRED.value,
                "confirmed_by": None,
            }
        ],
    }

    # Before confirmation: Phone is excluded, names Vicky vs Vikram are dissimilar -> no suggestion
    sugs_before = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs_before) == 0

    # After confirmation: confirmed_by is set -> phone is eligible!
    new_person_confirmed = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "canonical_name": "Vicky",
        "identifiers": [
            {
                "type": "phone",
                "value": "+919876543210",
                "trust": IdentifierTrust.REVIEW_REQUIRED.value,
                "confirmed_by": "analyst_1",
            }
        ],
    }
    sugs_after = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person_confirmed],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs_after) == 1
    assert sugs_after[0].status == SuggestionStatus.NEEDS_REVIEW


@pytest.mark.gate3
def test_rejected_pair_suppression_and_resurfacing(empty_store: SqliteEntityStore) -> None:
    from atlas.contracts.records import ReviewAction
    from atlas.resolve.review import apply_review_action

    empty_store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:p1",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
            "attributes": {"father_name": "Harbans Singh"},
        }
    )

    new_person = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "canonical_name": "Vicky",
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
    }

    # First run: suggestion is emitted
    sugs1 = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs1) == 1

    # Human reviewer rejects match
    rej_action = ReviewAction(
        action_id="ACT-REJ-VICKY",
        type=ReviewActionType.REJECT_MATCH,
        actor="analyst_1",
        at="2026-10-15T12:00:00Z",
        reason="Different individuals sharing device",
        target_ids=[new_person["person_id"], "PERSON:CASE-A-001:p1"],
        case_id="CASE-B-002",
        payload={"fingerprint": sugs1[0].signals},  # store signals fingerprint
        prev_hash="",
        entry_hash="",
    )
    # Compute fingerprint from signals
    from atlas.resolve.signals import compute_signal_fingerprint

    rej_action.payload["fingerprint"] = compute_signal_fingerprint(sugs1[0].signals)

    apply_review_action(empty_store, rej_action, auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]})

    # Second run with identical evidence: suppressed!
    sugs2 = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs2) == 0

    # Third run with NEW evidence (new address or father name): resurfaces!
    new_person_expanded = {
        **new_person,
        "attributes": {"father_name": "Harbans Singh"},
    }
    sugs3 = generate_suggestions(
        empty_store,
        current_case_id="CASE-B-002",
        new_persons=[new_person_expanded],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(sugs3) == 1
