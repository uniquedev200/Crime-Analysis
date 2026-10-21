"""Unit tests for SqliteEntityStore: storage, authorization filtering, and query isolation.

All tests marked with @pytest.mark.gate3.
"""

from __future__ import annotations

import pytest

from atlas.contracts.enums import EntityType, IdentifierTrust, Origin, QuoteStatus, SuggestionStatus, UnitKind
from atlas.contracts.records import Mention, ResolutionSuggestion, SourceRef
from atlas.resolve.store_sqlite import SqliteEntityStore


@pytest.fixture
def store() -> SqliteEntityStore:
    s = SqliteEntityStore(":memory:")
    yield s
    s.close()


def _make_source() -> SourceRef:
    return SourceRef(
        doc_id="DOC-001",
        file_name="fir.pdf",
        file_sha256="b" * 64,
        unit_id="DOC-001:p001",
        unit_kind=UnitKind.PAGE,
        page=1,
        text_origin=Origin.PDF_TEXT,
        quote="Test quote",
        quote_status=QuoteStatus.VERIFIED,
    )


@pytest.mark.gate3
def test_auth_filter_excludes_unauthorized_without_leak(store: SqliteEntityStore) -> None:
    # Populate store with Case A, Case B, and Secret Case X
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:p1",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-SECRET-X:p1",
            "case_id": "CASE-SECRET-X",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )

    # User authorized only for CASE-A-001 and CASE-B-002
    auth_allowed = {"allowed_cases": ["CASE-A-001", "CASE-B-002"]}
    cands = store.query_candidates(
        auth=auth_allowed,
        identifier_keys=["+919876543210"],
        name_keys=["vikram singh"],
        current_case_id="CASE-B-002",
    )
    # Only CASE-A-001 returned; CASE-SECRET-X strictly excluded
    assert len(cands) == 1
    assert cands[0]["case_id"] == "CASE-A-001"
    assert "CASE-SECRET-X" not in [c["case_id"] for c in cands]

    # User with zero allowed cases
    auth_empty = {"allowed_cases": []}
    cands_empty = store.query_candidates(
        auth=auth_empty,
        identifier_keys=["+919876543210"],
        name_keys=["vikram singh"],
        current_case_id="CASE-B-002",
    )
    assert len(cands_empty) == 0


@pytest.mark.gate3
def test_current_case_exclusion_cross_case_only(store: SqliteEntityStore) -> None:
    # Two persons in the same case (CASE-A-001) with the same phone
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:p1",
            "case_id": "CASE-A-001",
            "canonical_name": "Person One",
            "name_key": "person one",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-B-002:p2",
            "case_id": "CASE-B-002",
            "canonical_name": "Person Two",
            "name_key": "person two",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )

    # Query from CASE-A-001: should NOT return Person One (same case), should return Person Two (other case)
    cands = store.query_candidates(
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
        identifier_keys=["+919876543210"],
        name_keys=[],
        current_case_id="CASE-A-001",
    )
    assert len(cands) == 1
    assert cands[0]["person_id"] == "PERSON:CASE-B-002:p2"


@pytest.mark.gate3
def test_store_mentions_and_updates(store: SqliteEntityStore) -> None:
    source = _make_source()
    mention = Mention(
        mention_id="M-001",
        case_id="CASE-A-001",
        doc_id="DOC-001",
        type=EntityType.PHONE,
        surface_text="9876543210",
        normalized_value="+919876543210",
        origin=Origin.OCR,
        identifier_trust=IdentifierTrust.REVIEW_REQUIRED,
        source=source,
    )
    store.store_mentions("CASE-A-001", [mention])

    # Update mention trust and confirmation
    ok = store.update_mention_identifier("M-001", trust="strong", confirmed_by="analyst_1")
    assert ok is True

    # Retrieve and verify
    cursor = store._conn.cursor()
    cursor.execute("SELECT identifier_trust, confirmed_by FROM mentions WHERE mention_id = 'M-001'")
    row = cursor.fetchone()
    assert row["identifier_trust"] == "strong"
    assert row["confirmed_by"] == "analyst_1"


@pytest.mark.gate3
def test_store_and_query_suggestions(store: SqliteEntityStore) -> None:
    sug = ResolutionSuggestion(
        suggestion_id="SUG-001",
        case_id="CASE-B-002",
        mention_id="M-B-1",
        candidate_entity_id="PERSON:CASE-A-001:p1",
        candidate_case_id="CASE-A-001",
        status=SuggestionStatus.CANDIDATE,
        heuristic_rank=0.88,
        explanation="High confidence match",
    )
    store.store_suggestions("CASE-B-002", [sug])

    # Query with authorized user
    res_auth = store.get_suggestions("CASE-B-002", auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]})
    assert len(res_auth) == 1
    assert res_auth[0]["candidate_case_id"] == "CASE-A-001"

    # Query with user not authorized for candidate case: candidate_case_id obscured
    res_unauth = store.get_suggestions("CASE-B-002", auth={"allowed_cases": ["CASE-B-002"]})
    assert len(res_unauth) == 1
    assert res_unauth[0]["candidate_case_id"] is None


@pytest.mark.gate3
def test_merge_links_and_rejected_pairs(store: SqliteEntityStore) -> None:
    # Merge links
    store.store_merge_link(
        {
            "link_id": "ML-001",
            "case_id": "CASE-001",
            "entity_id_1": "E1",
            "entity_id_2": "E2",
            "action_id": "ACT-001",
            "status": "active",
        }
    )
    links = store.get_merge_links("CASE-001")
    assert len(links) == 1
    assert links[0]["entity_id_1"] == "E1"

    # Rejected pairs
    store.store_rejected_pair(
        {
            "rejection_id": "REJ-001",
            "case_id": "CASE-001",
            "entity_id_1": "E1",
            "entity_id_2": "E3",
            "fingerprint": "fp123",
            "action_id": "ACT-002",
        }
    )
    rejections = store.get_rejected_pairs("CASE-001")
    assert len(rejections) == 1
    assert rejections[0]["fingerprint"] == "fp123"


@pytest.mark.gate3
def test_case_persons_and_nodes_dedicated_methods(store: SqliteEntityStore) -> None:
    # 1. Store and get case person
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-1:p1",
            "case_id": "CASE-1",
            "cluster_id": "c1",
            "canonical_name": "Arun Sharma",
            "name_key": "arun sharma",
            "name_variants": ["A. Sharma"],
            "aliases": ["Sunny"],
            "attributes": {"age": 30},
            "mention_ids": ["M1"],
            "identifiers": [{"type": "phone", "value": "+919800011122", "trust": "strong"}],
            "co_occurrences": [],
        }
    )
    p = store.get_case_person("PERSON:CASE-1:p1")
    assert p is not None
    assert p["canonical_name"] == "Arun Sharma"

    p_none = store.get_case_person("NON_EXISTENT")
    assert p_none is None

    all_p = store.get_case_persons()
    assert len(all_p) >= 1

    case1_p = store.get_case_persons("CASE-1")
    assert len(case1_p) == 1

    # 2. Store, get, update identifier node
    store.store_identifier_node(
        {
            "node_id": "PHONE:+919800011122",
            "identifier_type": "phone",
            "normalized_value": "+919800011122",
            "raw_value": "9800011122",
            "trust": "review_required",
            "case_ids": ["CASE-1"],
            "mention_ids": ["M1"],
        }
    )
    nodes = store.get_identifier_nodes("CASE-1")
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "PHONE:+919800011122"

    # Filter by non-existent case
    assert len(store.get_identifier_nodes("CASE-NON-EXISTENT")) == 0

    # Update node
    ok_up = store.update_identifier_node(
        "PHONE:+919800011122",
        trust="strong",
        confirmed_by="analyst_1",
        normalized_value="+919800011122",
    )
    assert ok_up is True
    assert store.update_identifier_node("NON_EXISTENT") is False

    # 3. Store and get aliases
    store.store_alias(
        {
            "alias_id": "ALIAS-1",
            "case_id": "CASE-1",
            "person_id": "PERSON:CASE-1:p1",
            "primary_name": "Arun Sharma",
            "alias_name": "Sunny",
            "primary_name_key": "arun sharma",
            "alias_name_key": "sunny",
            "source_mention_id": "M1",
        }
    )
    aliases = store.get_aliases("CASE-1")
    assert len(aliases) == 1
    assert aliases[0]["alias_name"] == "Sunny"
    assert len(store.get_aliases()) >= 1


@pytest.mark.gate3
def test_record_action_formats_and_errors(store: SqliteEntityStore) -> None:
    # Action as dict
    action_dict = {
        "action_id": "ACT-DICT-1",
        "type": "APPROVE_MATCH",
        "actor": "analyst_1",
        "at": "2026-10-15T12:00:00Z",
        "reason": "Dict format test",
        "target_ids": ["E1", "E2"],
        "payload": {},
        "prev_hash": "0" * 64,
        "entry_hash": "a" * 64,
        "case_id": "CASE-1",
    }
    store.record_action(action_dict)
    entries = store.get_audit_entries("CASE-1")
    assert len(entries) == 1
    assert entries[0]["action_id"] == "ACT-DICT-1"

    # Invalid action type
    with pytest.raises(TypeError):
        store.record_action(99999)


@pytest.mark.gate3
def test_query_candidates_with_auth_object(store: SqliteEntityStore) -> None:
    class CustomAuth:
        def __init__(self) -> None:
            self.allowed_cases = ["CASE-1"]
            self.current_case = "CASE-2"

    store.store_case_person(
        {
            "person_id": "PERSON:CASE-1:p1",
            "case_id": "CASE-1",
            "canonical_name": "Test Person",
            "name_key": "test person",
            "identifiers": [{"type": "phone", "value": "+919811111111", "trust": "strong"}],
        }
    )

    cands = store.query_candidates(
        auth=CustomAuth(),
        identifier_keys=["+919811111111"],
        name_keys=["test person"],
    )
    assert len(cands) == 1
    assert cands[0]["person_id"] == "PERSON:CASE-1:p1"
