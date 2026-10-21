"""Review action processing, entity merge/split lifecycles, and audit logging.

Applies human decisions (CONFIRM_IDENTIFIER, CORRECT_IDENTIFIER, APPROVE_MATCH,
REJECT_MATCH, MERGE, SPLIT, RESOLVE_ITEM) with authorization and staleness validation.
"""

from __future__ import annotations

from typing import Any

from atlas.contracts.enums import IdentifierTrust, ReviewActionType
from atlas.contracts.records import ReviewAction
from atlas.resolve.audit import compute_entry_hash
from atlas.resolve.store_sqlite import SqliteEntityStore


def apply_review_action(
    store: SqliteEntityStore,
    action: ReviewAction,
    auth: Any,
) -> tuple[bool, str]:
    """Validate authorization, verify before_state staleness, execute action, and record audit log.

    Returns:
        tuple[bool, str]: (success, message_or_error_detail)
    """
    # 1. Authorization check
    allowed_cases: set[str] | None = None
    if auth is not None:
        if isinstance(auth, dict):
            raw = auth.get("allowed_cases")
            if raw is not None:
                allowed_cases = set(raw)
        elif hasattr(auth, "allowed_cases"):
            raw = auth.allowed_cases
            if raw is not None:
                allowed_cases = set(raw)

    if allowed_cases is not None:
        target_case = action.case_id
        if target_case and target_case not in allowed_cases:
            return False, f"Unauthorized: actor '{action.actor}' is not authorized for case '{target_case}'"

    # 2. Staleness / before_state check
    action_type = action.type
    if isinstance(action_type, str):
        import contextlib

        with contextlib.suppress(ValueError):
            action_type = ReviewActionType(action_type)

    if action.before_state is not None:
        # Check current state based on action type
        if action_type in (ReviewActionType.CONFIRM_IDENTIFIER, ReviewActionType.CORRECT_IDENTIFIER):
            if action.target_ids:
                target_id = action.target_ids[0]
                cursor = store._conn.cursor()
                cursor.execute(
                    "SELECT identifier_trust, confirmed_by, normalized_value FROM mentions WHERE mention_id = ?",
                    (target_id,),
                )
                row = cursor.fetchone()
                if row:
                    curr_state = {
                        "trust": row["identifier_trust"],
                        "confirmed_by": row["confirmed_by"],
                        "normalized_value": row["normalized_value"],
                    }
                    for k, expected_v in action.before_state.items():
                        if curr_state.get(k) != expected_v:
                            return (
                                False,
                                f"Stale action: before_state mismatch for key '{k}' ({curr_state.get(k)} != {expected_v})",
                            )
                else:
                    cursor.execute(
                        "SELECT trust, confirmed_by, normalized_value FROM identifier_nodes WHERE node_id = ?",
                        (target_id,),
                    )
                    node_row = cursor.fetchone()
                    if node_row:
                        curr_state = {
                            "trust": node_row["trust"],
                            "confirmed_by": node_row["confirmed_by"],
                            "normalized_value": node_row["normalized_value"],
                        }
                        for k, expected_v in action.before_state.items():
                            if curr_state.get(k) != expected_v:
                                return (
                                    False,
                                    f"Stale action: before_state mismatch for key '{k}' ({curr_state.get(k)} != {expected_v})",
                                )

        elif action_type == ReviewActionType.SPLIT and len(action.target_ids) >= 2:
            e1, e2 = action.target_ids[0], action.target_ids[1]
            links = store.get_merge_links(case_id=action.case_id)
            active = any(
                link["status"] == "active"
                and (
                    (link["entity_id_1"] == e1 and link["entity_id_2"] == e2)
                    or (link["entity_id_1"] == e2 and link["entity_id_2"] == e1)
                )
                for link in links
            )
            if not active:
                return False, "Stale action: active merge link does not exist to split"

    # 3. Execute action
    after_state: dict[str, Any] = dict(action.after_state or {})

    if action_type == ReviewActionType.CONFIRM_IDENTIFIER:
        for tid in action.target_ids:
            store.update_mention_identifier(
                tid,
                trust=IdentifierTrust.STRONG.value,
                confirmed_by=action.actor,
            )
            store.update_identifier_node(
                tid,
                trust=IdentifierTrust.STRONG.value,
                confirmed_by=action.actor,
            )
        after_state.setdefault("trust", IdentifierTrust.STRONG.value)
        after_state.setdefault("confirmed_by", action.actor)

    elif action_type == ReviewActionType.CORRECT_IDENTIFIER:
        corrected_val = action.payload.get("corrected_value")
        if not corrected_val:
            return False, "CORRECT_IDENTIFIER requires 'corrected_value' in payload"
        for tid in action.target_ids:
            store.update_mention_identifier(
                tid,
                trust=IdentifierTrust.STRONG.value,
                confirmed_by=action.actor,
                normalized_value=corrected_val,
            )
            store.update_identifier_node(
                tid,
                trust=IdentifierTrust.STRONG.value,
                confirmed_by=action.actor,
                normalized_value=corrected_val,
            )
        after_state.setdefault("normalized_value", corrected_val)
        after_state.setdefault("confirmed_by", action.actor)
        after_state.setdefault("trust", IdentifierTrust.STRONG.value)

    elif action_type in (ReviewActionType.APPROVE_MATCH, ReviewActionType.MERGE):
        if len(action.target_ids) < 2:
            return False, f"{action_type} requires at least two target entity IDs"
        e1, e2 = action.target_ids[0], action.target_ids[1]
        link_id = f"ML-{action.action_id}"
        case_id = action.case_id or "CROSS_CASE"
        store.store_merge_link(
            {
                "link_id": link_id,
                "case_id": case_id,
                "entity_id_1": e1,
                "entity_id_2": e2,
                "action_id": action.action_id,
                "status": "active",
            }
        )
        after_state["merged_pair"] = [e1, e2]
        after_state["link_id"] = link_id
        after_state["status"] = "active"

    elif action_type == ReviewActionType.REJECT_MATCH:
        if len(action.target_ids) < 2:
            return False, "REJECT_MATCH requires at least two target entity IDs"
        e1, e2 = action.target_ids[0], action.target_ids[1]
        rejection_id = f"REJ-{action.action_id}"
        fingerprint = action.payload.get("fingerprint", "")
        case_id = action.case_id or "CROSS_CASE"
        store.store_rejected_pair(
            {
                "rejection_id": rejection_id,
                "case_id": case_id,
                "entity_id_1": e1,
                "entity_id_2": e2,
                "fingerprint": fingerprint,
                "action_id": action.action_id,
            }
        )
        after_state["rejected_pair"] = [e1, e2]
        after_state["fingerprint"] = fingerprint

    elif action_type == ReviewActionType.SPLIT:
        if len(action.target_ids) < 2:
            return False, "SPLIT requires at least two target entity IDs"
        e1, e2 = action.target_ids[0], action.target_ids[1]
        links = store.get_merge_links(case_id=action.case_id)
        found = False
        for link in links:
            if link["status"] == "active" and (
                (link["entity_id_1"] == e1 and link["entity_id_2"] == e2)
                or (link["entity_id_1"] == e2 and link["entity_id_2"] == e1)
                or (link["link_id"] in action.target_ids)
            ):
                store.store_merge_link({**link, "status": "split"})
                found = True
        if not found:
            return False, f"SPLIT failed: active merge link between {e1} and {e2} not found"
        after_state["split_pair"] = [e1, e2]
        after_state["status"] = "split"

    elif action_type == ReviewActionType.RESOLVE_ITEM:
        after_state["status"] = "resolved"

    # 4. Hash chain logging
    prev_hash = store.get_latest_audit_hash()
    action_dict = action.model_dump()
    action_dict["prev_hash"] = prev_hash
    action_dict["after_state"] = after_state

    # Compute entry_hash
    action_entry_hash = compute_entry_hash(prev_hash, action_dict)
    action_dict["entry_hash"] = action_entry_hash

    # Save to store
    store.record_action(action_dict)

    return True, f"Action {action_type} applied and audited successfully"


__all__ = ["apply_review_action"]
