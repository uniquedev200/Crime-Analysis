"""Unit tests for audit trail integrity, review actions, and resolver read-only invariants.

All tests marked with @pytest.mark.gate3.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.contracts.enums import IdentifierTrust, ReviewActionType
from atlas.contracts.records import ReviewAction
from atlas.resolve.audit import GENESIS_HASH, verify_chain
from atlas.resolve.candidates import generate_suggestions
from atlas.resolve.review import apply_review_action
from atlas.resolve.store_sqlite import SqliteEntityStore


@pytest.fixture
def store() -> SqliteEntityStore:
    s = SqliteEntityStore(":memory:")
    yield s
    s.close()


@pytest.mark.gate3
def test_clean_audit_log_verify_chain_passes(store: SqliteEntityStore) -> None:
    # Empty log returns True
    assert store.verify_chain() is True

    # Record first action
    act1 = ReviewAction(
        action_id="ACT-001",
        type=ReviewActionType.APPROVE_MATCH,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Verified match on confirmed phone",
        target_ids=["E1", "E2"],
        case_id="CASE-A-001",
        prev_hash=GENESIS_HASH,
        entry_hash="",  # Computed by apply_review_action
    )
    ok1, _msg1 = apply_review_action(store, act1, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok1 is True

    # Record second action
    act2 = ReviewAction(
        action_id="ACT-002",
        type=ReviewActionType.CONFIRM_IDENTIFIER,
        actor="analyst_2",
        at="2026-10-15T10:05:00Z",
        reason="OCR digits confirmed against image crop",
        target_ids=["M-001"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok2, _msg2 = apply_review_action(store, act2, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok2 is True

    # Validate chain
    assert store.verify_chain() is True
    assert verify_chain(store) is True


@pytest.mark.gate3
def test_tampering_one_audit_row_causes_verify_chain_to_fail(store: SqliteEntityStore) -> None:
    # Record 3 actions
    for i in range(1, 4):
        act = ReviewAction(
            action_id=f"ACT-00{i}",
            type=ReviewActionType.APPROVE_MATCH,
            actor="analyst_1",
            at=f"2026-10-15T10:0{i}:00Z",
            reason=f"Action {i}",
            target_ids=[f"E{i}", f"E{i + 1}"],
            case_id="CASE-A-001",
            prev_hash="",
            entry_hash="",
        )
        ok, _ = apply_review_action(store, act, auth={"allowed_cases": ["CASE-A-001"]})
        assert ok is True

    # Verify clean log passes
    assert store.verify_chain() is True

    # Tamper with row 2's reason
    cursor = store._conn.cursor()
    cursor.execute("UPDATE audit_log SET reason = 'Tampered reason' WHERE action_id = 'ACT-002'")
    store._conn.commit()

    # Now verify_chain MUST return False
    assert store.verify_chain() is False


@pytest.mark.gate3
def test_approve_match_creates_merge_link_and_split_reverses(store: SqliteEntityStore) -> None:
    # 1. Approve match
    act_merge = ReviewAction(
        action_id="ACT-M1",
        type=ReviewActionType.MERGE,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Approve cross-case merge",
        target_ids=["PERSON:CASE-A:1", "PERSON:CASE-B:2"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok, _msg = apply_review_action(store, act_merge, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok is True

    links = store.get_merge_links("CASE-A-001")
    assert len(links) == 1
    assert links[0]["status"] == "active"
    assert links[0]["entity_id_1"] == "PERSON:CASE-A:1"
    assert links[0]["entity_id_2"] == "PERSON:CASE-B:2"

    # 2. Split reverses the merge
    act_split = ReviewAction(
        action_id="ACT-S1",
        type=ReviewActionType.SPLIT,
        actor="senior_analyst",
        at="2026-10-15T10:30:00Z",
        reason="Reverse prior merge upon new contradictory evidence",
        target_ids=["PERSON:CASE-A:1", "PERSON:CASE-B:2"],
        case_id="CASE-A-001",
        before_state={"status": "active"},
        prev_hash="",
        entry_hash="",
    )
    ok_split, _msg_split = apply_review_action(store, act_split, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_split is True

    # Link status must now be 'split'
    links_after = store.get_merge_links("CASE-A-001")
    assert len(links_after) == 1
    assert links_after[0]["status"] == "split"


@pytest.mark.gate3
def test_unauthorized_action_rejected(store: SqliteEntityStore) -> None:
    # Actor only permitted for CASE-A-001 attempts action on CASE-B-002
    act = ReviewAction(
        action_id="ACT-UNAUTH",
        type=ReviewActionType.APPROVE_MATCH,
        actor="restricted_analyst",
        at="2026-10-15T10:00:00Z",
        reason="Attempted unauthorized approve",
        target_ids=["E1", "E2"],
        case_id="CASE-B-002",
        prev_hash="",
        entry_hash="",
    )
    ok, msg = apply_review_action(store, act, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok is False
    assert "Unauthorized" in msg

    # Audit log should NOT have recorded this failed action
    assert len(store.get_audit_entries()) == 0


@pytest.mark.gate3
def test_stale_action_rejected(store: SqliteEntityStore) -> None:
    # Seed a mention that was already confirmed
    cursor = store._conn.cursor()
    cursor.execute(
        """
        INSERT INTO mentions (
            mention_id, case_id, doc_id, type, surface_text,
            normalized_value, normalization_status, stated_role,
            origin, identifier_trust, confirmed_by, source_json, data_json
        ) VALUES ('M-100', 'CASE-A-001', 'DOC-1', 'phone', '9876543210',
                  '+919876543210', 'ok', 'suspect', 'ocr', 'strong', 'first_reviewer', '{}', '{}')
        """
    )
    store._conn.commit()

    # Second reviewer tries to confirm with stale before_state expecting unconfirmed/review_required
    stale_action = ReviewAction(
        action_id="ACT-STALE",
        type=ReviewActionType.CONFIRM_IDENTIFIER,
        actor="second_reviewer",
        at="2026-10-15T10:00:00Z",
        reason="Confirming from stale UI state",
        target_ids=["M-100"],
        case_id="CASE-A-001",
        before_state={"trust": "review_required", "confirmed_by": None},
        prev_hash="",
        entry_hash="",
    )
    ok, msg = apply_review_action(store, stale_action, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok is False
    assert "Stale action" in msg


@pytest.mark.gate3
def test_resolver_never_calls_write_on_canonical_entities_spy_test(store: SqliteEntityStore) -> None:
    """Spy test verifying resolver suggestion generation is strictly read-only on the entity store."""
    # Seed person
    store.store_case_person(
        {
            "person_id": "PERSON:CASE-A-001:p1",
            "case_id": "CASE-A-001",
            "canonical_name": "Vikram Singh",
            "name_key": "vikram singh",
            "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
        }
    )

    # Wrap mutating methods with spies
    store.store_mentions = MagicMock(side_effect=store.store_mentions)  # type: ignore[method-assign]
    store.store_case_person = MagicMock(side_effect=store.store_case_person)  # type: ignore[method-assign]
    store.store_identifier_node = MagicMock(side_effect=store.store_identifier_node)  # type: ignore[method-assign]
    store.store_merge_link = MagicMock(side_effect=store.store_merge_link)  # type: ignore[method-assign]
    store.store_rejected_pair = MagicMock(side_effect=store.store_rejected_pair)  # type: ignore[method-assign]
    store.record_action = MagicMock(side_effect=store.record_action)  # type: ignore[method-assign]

    new_person = {
        "person_id": "PERSON:CASE-B-002:vicky",
        "case_id": "CASE-B-002",
        "canonical_name": "Vicky",
        "identifiers": [{"type": "phone", "value": "+919876543210", "trust": "strong"}],
    }

    # Generate suggestions
    suggestions = generate_suggestions(
        store,
        current_case_id="CASE-B-002",
        new_persons=[new_person],
        auth={"allowed_cases": ["CASE-A-001", "CASE-B-002"]},
    )
    assert len(suggestions) == 1

    # Assert zero write calls were made
    assert store.store_mentions.call_count == 0
    assert store.store_case_person.call_count == 0
    assert store.store_identifier_node.call_count == 0
    assert store.store_merge_link.call_count == 0
    assert store.store_rejected_pair.call_count == 0
    assert store.record_action.call_count == 0


@pytest.mark.gate3
def test_correct_identifier_action(store: SqliteEntityStore) -> None:
    # Seed mention and identifier node
    cursor = store._conn.cursor()
    cursor.execute(
        """
        INSERT INTO mentions (
            mention_id, case_id, doc_id, type, surface_text,
            normalized_value, normalization_status, stated_role,
            origin, identifier_trust, confirmed_by, source_json, data_json
        ) VALUES ('M-CORR', 'CASE-A-001', 'DOC-1', 'phone', '9876543210',
                  '+919876543210', 'ok', 'suspect', 'ocr', 'review_required', NULL, '{}', '{}')
        """
    )
    store.store_identifier_node(
        {
            "node_id": "PHONE:+919876543210",
            "identifier_type": "phone",
            "normalized_value": "+919876543210",
            "raw_value": "9876543210",
            "trust": "review_required",
            "case_ids": ["CASE-A-001"],
            "mention_ids": ["M-CORR"],
        }
    )

    # 1. Test missing corrected_value in payload
    act_missing = ReviewAction(
        action_id="ACT-CORR-BAD",
        type=ReviewActionType.CORRECT_IDENTIFIER,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Missing correction",
        target_ids=["M-CORR"],
        case_id="CASE-A-001",
        payload={},
        prev_hash="",
        entry_hash="",
    )
    ok_bad, msg_bad = apply_review_action(store, act_missing, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_bad is False
    assert "corrected_value" in msg_bad

    # 2. Test valid correction
    act_good = ReviewAction(
        action_id="ACT-CORR-OK",
        type=ReviewActionType.CORRECT_IDENTIFIER,
        actor="analyst_1",
        at="2026-10-15T10:01:00Z",
        reason="Correcting misread OCR digit 0 to 9",
        target_ids=["M-CORR", "PHONE:+919876543210"],
        case_id="CASE-A-001",
        payload={"corrected_value": "+919876543219"},
        prev_hash="",
        entry_hash="",
    )
    ok_good, _msg_good = apply_review_action(store, act_good, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_good is True

    # Verify updated state in DB
    cursor.execute("SELECT normalized_value, identifier_trust, confirmed_by FROM mentions WHERE mention_id = 'M-CORR'")
    row = cursor.fetchone()
    assert row["normalized_value"] == "+919876543219"
    assert row["identifier_trust"] == IdentifierTrust.STRONG.value
    assert row["confirmed_by"] == "analyst_1"


@pytest.mark.gate3
def test_reject_match_and_resolve_item(store: SqliteEntityStore) -> None:
    # 1. Reject match bad targets
    act_rej_bad = ReviewAction(
        action_id="ACT-REJ-BAD",
        type=ReviewActionType.REJECT_MATCH,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Reject with 1 target",
        target_ids=["E1"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok_b, _ = apply_review_action(store, act_rej_bad, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_b is False

    # 2. Valid reject match
    act_rej_good = ReviewAction(
        action_id="ACT-REJ-OK",
        type=ReviewActionType.REJECT_MATCH,
        actor="analyst_1",
        at="2026-10-15T10:01:00Z",
        reason="Entities are distinct persons",
        target_ids=["E1", "E2"],
        case_id="CASE-A-001",
        payload={"fingerprint": "fp_test_123"},
        prev_hash="",
        entry_hash="",
    )
    ok_g, _ = apply_review_action(store, act_rej_good, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_g is True

    rejections = store.get_rejected_pairs("CASE-A-001")
    assert len(rejections) == 1
    assert rejections[0]["fingerprint"] == "fp_test_123"

    # 3. Resolve item
    act_item = ReviewAction(
        action_id="ACT-ITEM-1",
        type=ReviewActionType.RESOLVE_ITEM,
        actor="analyst_1",
        at="2026-10-15T10:02:00Z",
        reason="Review item addressed",
        target_ids=["REV-001"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok_item, _ = apply_review_action(store, act_item, auth={"allowed_cases": ["CASE-A-001"]})
    assert ok_item is True


@pytest.mark.gate3
def test_review_action_auth_object_and_split_errors(store: SqliteEntityStore) -> None:
    class MockAuth:
        def __init__(self) -> None:
            self.allowed_cases = ["CASE-A-001"]

    # Action on unauthorized case
    act_unauth = ReviewAction(
        action_id="ACT-OBJ-UNAUTH",
        type=ReviewActionType.APPROVE_MATCH,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Test auth object",
        target_ids=["E1", "E2"],
        case_id="CASE-B-002",
        prev_hash="",
        entry_hash="",
    )
    ok_unauth, _ = apply_review_action(store, act_unauth, auth=MockAuth())
    assert ok_unauth is False

    # Split with < 2 targets
    act_split_bad = ReviewAction(
        action_id="ACT-SPLIT-1",
        type=ReviewActionType.SPLIT,
        actor="analyst_1",
        at="2026-10-15T10:01:00Z",
        reason="Split with 1 target",
        target_ids=["E1"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok_sb, _ = apply_review_action(store, act_split_bad, auth=MockAuth())
    assert ok_sb is False

    # Split non-existent link
    act_split_missing = ReviewAction(
        action_id="ACT-SPLIT-2",
        type=ReviewActionType.SPLIT,
        actor="analyst_1",
        at="2026-10-15T10:02:00Z",
        reason="Split missing link",
        target_ids=["E1", "E2"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    ok_sm, msg_sm = apply_review_action(store, act_split_missing, auth=MockAuth())
    assert ok_sm is False
    assert "not found" in msg_sm


@pytest.mark.gate3
def test_audit_edge_cases_and_type_errors(store: SqliteEntityStore) -> None:
    from atlas.resolve.audit import compute_entry_hash, get_canonical_action_payload

    with pytest.raises(TypeError):
        get_canonical_action_payload(12345)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        compute_entry_hash(GENESIS_HASH, 12345)  # type: ignore[arg-type]

    # Test prev_hash mismatch detection in verify_chain
    act = ReviewAction(
        action_id="ACT-CHAIN-1",
        type=ReviewActionType.APPROVE_MATCH,
        actor="analyst_1",
        at="2026-10-15T10:00:00Z",
        reason="Chain test",
        target_ids=["E1", "E2"],
        case_id="CASE-A-001",
        prev_hash="",
        entry_hash="",
    )
    apply_review_action(store, act, auth={"allowed_cases": ["CASE-A-001"]})

    # Break prev_hash
    cursor = store._conn.cursor()
    cursor.execute("UPDATE audit_log SET prev_hash = 'bad_hash' WHERE action_id = 'ACT-CHAIN-1'")
    store._conn.commit()
    assert store.verify_chain() is False
