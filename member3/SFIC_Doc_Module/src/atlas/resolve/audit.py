"""Audit log integrity, canonical hashing, and cryptographic chain verification.

All review decisions are recorded in an append-only hash chain:
entry_hash = sha256(prev_hash + canonical_json(payload))
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from atlas.contracts.records import ReviewAction

GENESIS_HASH: Final[str] = "0" * 64


def canonical_json(data: Any) -> str:
    """Serialize data to deterministic canonical UTF-8 JSON.

    Sorted keys, compact separators, UTF-8 strings.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def get_canonical_action_payload(action: ReviewAction | dict[str, Any]) -> dict[str, Any]:
    """Extract standard deterministic dictionary representation of a review action."""
    if isinstance(action, ReviewAction):
        action_type = action.type.value if hasattr(action.type, "value") else str(action.type)
        return {
            "action_id": action.action_id,
            "actor": action.actor,
            "after_state": action.after_state or {},
            "at": action.at,
            "before_state": action.before_state or {},
            "case_id": action.case_id,
            "payload": action.payload or {},
            "reason": action.reason,
            "target_ids": sorted(action.target_ids),
            "type": action_type,
        }
    if isinstance(action, dict):
        payload = action.get("payload") or {}
        before_state = action.get("before_state") or {}
        after_state = action.get("after_state") or {}
        target_ids = sorted(action.get("target_ids") or [])
        action_type = action.get("type", "")
        if hasattr(action_type, "value"):
            action_type = action_type.value
        return {
            "action_id": action.get("action_id", ""),
            "actor": action.get("actor", ""),
            "after_state": after_state,
            "at": action.get("at", ""),
            "before_state": before_state,
            "case_id": action.get("case_id"),
            "payload": payload,
            "reason": action.get("reason", ""),
            "target_ids": target_ids,
            "type": str(action_type),
        }
    raise TypeError(f"Expected ReviewAction or dict, got {type(action).__name__}")


def compute_entry_hash(prev_hash: str, payload_data: Any) -> str:
    """Compute deterministic SHA-256 hash for an audit log entry.

    Accepts a ReviewAction, a full action dict, or a raw payload dictionary.
    """
    if isinstance(payload_data, ReviewAction) or (
        isinstance(payload_data, dict) and "action_id" in payload_data and "type" in payload_data
    ):
        canonical_dict = get_canonical_action_payload(payload_data)
    elif isinstance(payload_data, dict):
        canonical_dict = payload_data
    else:
        raise TypeError(f"Unsupported payload type for entry hash: {type(payload_data).__name__}")

    raw_json = canonical_json(canonical_dict)
    combined = (prev_hash + raw_json).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def verify_chain(store: Any) -> bool:
    """Validate hash chain integrity across all audit log rows in the entity store.

    Returns True if the entire chain is valid and untampered, False otherwise.
    """
    rows = store.get_audit_entries()
    if not rows:
        return True

    expected_prev = GENESIS_HASH
    for row in rows:
        prev_hash = row.get("prev_hash")
        entry_hash = row.get("entry_hash")
        if prev_hash != expected_prev:
            return False

        # Reconstruct canonical payload for hashing
        payload_data = {
            "action_id": row.get("action_id", ""),
            "actor": row.get("actor", ""),
            "after_state": row.get("after_state") or {},
            "at": row.get("at", ""),
            "before_state": row.get("before_state") or {},
            "case_id": row.get("case_id"),
            "payload": row.get("payload") or {},
            "reason": row.get("reason", ""),
            "target_ids": sorted(row.get("target_ids") or []),
            "type": str(row.get("type", "")),
        }

        recalculated = compute_entry_hash(prev_hash, payload_data)
        if entry_hash != recalculated:
            return False

        expected_prev = entry_hash

    return True


__all__ = [
    "GENESIS_HASH",
    "canonical_json",
    "compute_entry_hash",
    "get_canonical_action_payload",
    "verify_chain",
]
