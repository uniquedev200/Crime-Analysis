"""Integration test for cross-case entity resolution on synthetic dataset.

All tests marked with @pytest.mark.gate3.
Simulates Case A intake followed by Case B intake, generating cross-case
suggestions, validating Vicky(B) vs Vikram Singh(A) needs_review,
handling hard negative correctly, and verifying audited merge and split actions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from synth.names import (
    ARJUN_VERMA_A,
    POOJA_SHARMA_B,
    RAJESH_SHARMA_A,
    SUNITA_SHARMA_B,
    VICKY_B,
    VIKRAM_SINGH_A,
    VIKRAM_SINGH_HARD_NEG,
)

from atlas.contracts.enums import IdentifierTrust, ReviewActionType, SuggestionStatus
from atlas.contracts.records import ReviewAction
from atlas.resolve.audit import GENESIS_HASH
from atlas.resolve.candidates import generate_suggestions
from atlas.resolve.review import apply_review_action
from atlas.resolve.store_sqlite import SqliteEntityStore


@pytest.mark.gate3
def test_cross_case_resolution_pipeline_synthetic_dataset(tmp_path: Path) -> None:
    db_file = tmp_path / "entity_store.db"
    store = SqliteEntityStore(db_file)

    auth = {
        "user": "demo_analyst",
        "allowed_cases": ["CASE-A-001", "CASE-B-002"],
    }

    # -----------------------------------------------------------------------
    # Step 1: Process and store Case A entities (FIR_A, CDR_A, BANK_A)
    # -----------------------------------------------------------------------
    case_a_persons = [
        {
            "person_id": "PERSON:CASE-A-001:vikram",
            "case_id": "CASE-A-001",
            "cluster_id": "c_vikram_a",
            "canonical_name": VIKRAM_SINGH_A.name,
            "name_key": "vikram singh",
            "name_variants": list(VIKRAM_SINGH_A.name_variants),
            "aliases": list(VIKRAM_SINGH_A.aliases),
            "attributes": {
                "father_name": VIKRAM_SINGH_A.father_name,
                "age": VIKRAM_SINGH_A.age,
                "address": VIKRAM_SINGH_A.address,
                "gender": VIKRAM_SINGH_A.gender,
            },
            "mention_ids": ["M-A-1", "M-A-2"],
            "identifiers": [
                {"type": "phone", "value": VIKRAM_SINGH_A.phone, "trust": IdentifierTrust.STRONG.value},
                {"type": "imei", "value": VIKRAM_SINGH_A.imei, "trust": IdentifierTrust.STRONG.value},
                {"type": "vehicle", "value": VIKRAM_SINGH_A.vehicle, "trust": IdentifierTrust.STRONG.value},
                {"type": "account", "value": VIKRAM_SINGH_A.account, "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": ["ORG:DelhiTransCorp"],
        },
        {
            "person_id": "PERSON:CASE-A-001:rajesh",
            "case_id": "CASE-A-001",
            "cluster_id": "c_rajesh_a",
            "canonical_name": RAJESH_SHARMA_A.name,
            "name_key": "rajesh kumar sharma",
            "name_variants": list(RAJESH_SHARMA_A.name_variants),
            "aliases": [],
            "attributes": {
                "father_name": RAJESH_SHARMA_A.father_name,
                "age": RAJESH_SHARMA_A.age,
                "address": RAJESH_SHARMA_A.address,
            },
            "mention_ids": ["M-A-3"],
            "identifiers": [
                {"type": "phone", "value": RAJESH_SHARMA_A.phone, "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": [],
        },
        {
            "person_id": "PERSON:CASE-A-001:arjun",
            "case_id": "CASE-A-001",
            "cluster_id": "c_arjun_a",
            "canonical_name": ARJUN_VERMA_A.name,
            "name_key": "arjun verma",
            "name_variants": [],
            "aliases": [],
            "attributes": {
                "father_name": ARJUN_VERMA_A.father_name,
                "age": ARJUN_VERMA_A.age,
            },
            "mention_ids": ["M-A-4"],
            "identifiers": [
                {"type": "phone", "value": ARJUN_VERMA_A.phone, "trust": IdentifierTrust.STRONG.value},
            ],
            "co_occurrences": [],
        },
    ]

    for p in case_a_persons:
        store.store_case_person(p)

    # -----------------------------------------------------------------------
    # Step 2: Intake Case B entities (FIR_B, CDR_B)
    # -----------------------------------------------------------------------
    # 2a. Vicky (Case B accused with shared phone to Case A Vikram Singh)
    vicky_b = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "cluster_id": "c_vicky_b",
        "canonical_name": "Vicky",
        "name_key": "vicky",
        "name_variants": [],
        "aliases": [],
        "attributes": {
            "father_name": VICKY_B.father_name,
            "age": VICKY_B.age,
            "address": VICKY_B.address,
        },
        "mention_ids": ["M-B-1"],
        "identifiers": [
            {"type": "phone", "value": VICKY_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "co_occurrences": ["ORG:DelhiTransCorp"],
    }

    # 2b. Hard negative: Different Vikram Singh (different father, age, and phone)
    hard_neg_b = {
        "person_id": "PERSON:CASE-B-002:hard_neg",
        "case_id": "CASE-B-002",
        "cluster_id": "c_hard_neg",
        "canonical_name": VIKRAM_SINGH_HARD_NEG.name,
        "name_key": "vikram singh",
        "name_variants": [],
        "aliases": [],
        "attributes": {
            "father_name": VIKRAM_SINGH_HARD_NEG.father_name,  # Mohan Singh vs Harbans Singh
            "age": VIKRAM_SINGH_HARD_NEG.age,  # 48 vs 32
            "address": VIKRAM_SINGH_HARD_NEG.address,
        },
        "mention_ids": ["M-B-2"],
        "identifiers": [
            {"type": "phone", "value": VIKRAM_SINGH_HARD_NEG.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "co_occurrences": [],
    }

    # 2c. Family shared phone: Pooja & Sunita
    pooja_b = {
        "person_id": "PERSON:CASE-B-002:pooja",
        "case_id": "CASE-B-002",
        "canonical_name": POOJA_SHARMA_B.name,
        "name_key": "pooja sharma",
        "identifiers": [
            {"type": "phone", "value": POOJA_SHARMA_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": POOJA_SHARMA_B.age},
    }
    sunita_b = {
        "person_id": "PERSON:CASE-B-002:sunita",
        "case_id": "CASE-B-002",
        "canonical_name": SUNITA_SHARMA_B.name,
        "name_key": "sunita sharma",
        "identifiers": [
            {"type": "phone", "value": SUNITA_SHARMA_B.phone, "trust": IdentifierTrust.STRONG.value},
        ],
        "attributes": {"age": SUNITA_SHARMA_B.age},
    }

    # -----------------------------------------------------------------------
    # Step 3: Run candidate resolution on Case B
    # -----------------------------------------------------------------------
    case_b_persons = [vicky_b, hard_neg_b, pooja_b, sunita_b]
    suggestions = generate_suggestions(
        store=store,
        current_case_id="CASE-B-002",
        new_persons=case_b_persons,
        auth=auth,
    )

    # -----------------------------------------------------------------------
    # Step 4: Verify cross-case resolution suggestions
    # -----------------------------------------------------------------------
    # 4a. Vicky(B) ↔ Vikram Singh(A):
    # Matches on shared phone (+919876543210), but names are dissimilar ("Vicky" vs "Vikram Singh").
    # MUST produce status = NEEDS_REVIEW (never automatic merge).
    vicky_sugs = [s for s in suggestions if s.mention_id == "M-B-1"]
    assert len(vicky_sugs) == 1
    vicky_sug = vicky_sugs[0]
    assert vicky_sug.candidate_entity_id == "PERSON:CASE-A-001:vikram"
    assert vicky_sug.candidate_case_id == "CASE-A-001"
    assert vicky_sug.status == SuggestionStatus.NEEDS_REVIEW
    assert vicky_sug.requires_human_decision is True
    assert "heuristic ordering, not a probability" in vicky_sug.rank_note

    # 4b. Hard Negative Vikram Singh(B):
    # Has different phone (+919833344455), different father (Mohan vs Harbans), different age (48 vs 32).
    # If any suggestion exists against Vikram Singh(A), it MUST be marked AMBIGUOUS due to contradictions,
    # or no suggestion emitted.
    hard_neg_sugs = [s for s in suggestions if s.mention_id == "M-B-2"]
    for s in hard_neg_sugs:
        assert s.status != SuggestionStatus.CANDIDATE
        assert s.status == SuggestionStatus.AMBIGUOUS

    # Store suggestions in SQLite entity store
    store.store_suggestions("CASE-B-002", suggestions)
    saved_sugs = store.get_suggestions("CASE-B-002", auth=auth)
    assert len(saved_sugs) == len(suggestions)

    # -----------------------------------------------------------------------
    # Step 5: Review Action Workflow (Approve -> Hash Chain -> Split)
    # -----------------------------------------------------------------------
    # 5a. Human reviewer approves Vicky(B) ↔ Vikram Singh(A) match
    approve_action = ReviewAction(
        action_id="ACT-VICKY-APPROVE-01",
        type=ReviewActionType.APPROVE_MATCH,
        actor="lead_investigator",
        at="2026-10-15T14:00:00Z",
        reason="FIR_A stated 'Vikram Singh alias Vicky' and shared phone confirms identity",
        target_ids=[vicky_b["person_id"], "PERSON:CASE-A-001:vikram"],
        case_id="CASE-B-002",
        prev_hash=GENESIS_HASH,
        entry_hash="",
    )
    ok_app, _msg_app = apply_review_action(store, approve_action, auth=auth)
    assert ok_app is True

    # Verify merge link created
    active_links = store.get_merge_links("CASE-B-002")
    assert len(active_links) == 1
    assert active_links[0]["status"] == "active"

    # Verify audit chain integrity
    assert store.verify_chain() is True

    # 5b. Reversing match via SPLIT
    split_action = ReviewAction(
        action_id="ACT-VICKY-SPLIT-01",
        type=ReviewActionType.SPLIT,
        actor="lead_investigator",
        at="2026-10-15T15:00:00Z",
        reason="Separating entities per supervisor directive",
        target_ids=[vicky_b["person_id"], "PERSON:CASE-A-001:vikram"],
        case_id="CASE-B-002",
        prev_hash="",
        entry_hash="",
    )
    ok_split, _msg_split = apply_review_action(store, split_action, auth=auth)
    assert ok_split is True

    # Merge link status is now 'split'
    links_after_split = store.get_merge_links("CASE-B-002")
    assert len(links_after_split) == 1
    assert links_after_split[0]["status"] == "split"

    # Audit chain still verifies cleanly
    assert store.verify_chain() is True
    store.close()
