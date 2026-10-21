"""Adversarial test suite: Storage tampering detection and concurrent case isolation.

Tests coverage:
1. Mutating one byte of stored original causes verify_hash to raise IntegrityError.
2. Tampering with any row or field in the SQLite audit log causes store.verify_chain() to return False.
3. Running two cases simultaneously against a shared SQLite entity store yields zero cross-case contamination.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from atlas.contracts.enums import (
    EntityType,
    IdentifierTrust,
    Origin,
    QuoteStatus,
    ReviewActionType,
    SuggestionStatus,
    UnitKind,
)
from atlas.contracts.ids import make_action_id, make_mention_id, make_suggestion_id
from atlas.contracts.records import Mention, ResolutionSuggestion, ReviewAction, SourceRef
from atlas.errors import IntegrityError
from atlas.ingest.integrity import verify_hash
from atlas.ingest.originals import store_original
from atlas.resolve.audit import GENESIS_HASH, compute_entry_hash
from atlas.resolve.store_sqlite import SqliteEntityStore

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
def test_mutate_stored_original_byte_raises_integrity_error(tmp_path: Path) -> None:
    """Mutating even a single byte of a stored immutable original triggers IntegrityError."""
    source_file = tmp_path / "original_evidence.bin"
    original_bytes = b"VERIFIED_EVIDENCE_STREAM_DATA_0123456789"
    source_file.write_bytes(original_bytes)
    sha256 = hashlib.sha256(original_bytes).hexdigest().lower()

    data_dir = tmp_path / "store"
    stored_path = store_original(source_file, sha256, data_dir)

    # Initial verification passes
    verify_hash(stored_path, sha256)

    # Adversary removes read-only attribute and flips 1 byte
    os.chmod(stored_path, stat.S_IWRITE | stat.S_IREAD)
    tampered_bytes = bytearray(stored_path.read_bytes())
    tampered_bytes[0] ^= 0xFF  # Flip first byte
    stored_path.write_bytes(tampered_bytes)

    # verify_hash must detect mismatch and raise IntegrityError
    with pytest.raises(IntegrityError) as exc_info:
        verify_hash(stored_path, sha256)

    assert "File hash mismatch" in str(exc_info.value)


@pytest.mark.gate5
def test_tamper_sqlite_audit_log_fails_verify_chain(tmp_path: Path) -> None:
    """Tampering with any column in any row of the SQLite audit chain causes verify_chain to return False."""
    db_file = tmp_path / "test_audit.db"
    store = SqliteEntityStore(db_file)

    # Build sequential hash-chained audit actions
    actions: list[ReviewAction] = []
    prev_h = GENESIS_HASH

    for i in range(1, 4):
        action_id = f"ACT-test-00{i}"
        payload_data = {
            "action_id": action_id,
            "type": ReviewActionType.APPROVE_MATCH.value,
            "actor": "investigator_1",
            "at": datetime.now(UTC).isoformat(),
            "reason": f"Decision step {i}",
            "target_ids": [f"M-00{i}"],
            "case_id": "CASE-AUDIT-01",
            "payload": {"step": i},
            "before_state": {},
            "after_state": {},
        }
        entry_h = compute_entry_hash(prev_h, payload_data)
        action = ReviewAction(
            action_id=action_id,
            case_id="CASE-AUDIT-01",
            type=ReviewActionType.APPROVE_MATCH,
            actor="investigator_1",
            at=payload_data["at"],
            reason=payload_data["reason"],
            target_ids=[f"M-00{i}"],
            payload={"step": i},
            prev_hash=prev_h,
            entry_hash=entry_h,
        )
        store.record_action(action)
        actions.append(action)
        prev_h = entry_h

    # Initial chain is verified
    assert store.verify_chain() is True

    # Tamper with row 2's reason
    cursor = store._conn.cursor()
    cursor.execute("UPDATE audit_log SET reason = 'Tampered reason by attacker' WHERE entry_id = 2")
    store._conn.commit()

    # Chain verification must now fail
    assert store.verify_chain() is False

    # Restore and verify that tampering with prev_hash also fails
    cursor.execute("UPDATE audit_log SET reason = 'Decision step 2' WHERE entry_id = 2")
    cursor.execute("UPDATE audit_log SET prev_hash = 'bad_prev_hash' WHERE entry_id = 3")
    store._conn.commit()
    assert store.verify_chain() is False

    store.close()


@pytest.mark.gate5
def test_concurrent_cases_in_shared_sqlite_store_zero_contamination(tmp_path: Path) -> None:
    """Two cases running concurrently against a shared SQLite entity store exhibit zero cross-case contamination."""
    db_file = tmp_path / "shared_entity_store.db"
    store = SqliteEntityStore(db_file)

    case_a = "CASE_ALPHA"
    case_b = "CASE_BETA"
    db_lock = threading.Lock()

    def populate_case(case_id: str, prefix: str) -> None:
        # Create unique mentions for this case
        mentions: list[Mention] = []
        for i in range(3):
            m_id = make_mention_id(f"DOC-{prefix}", f"DOC-{prefix}:p001", "PERSON", f"{prefix}_Person_{i}", i)
            m = Mention(
                mention_id=m_id,
                case_id=case_id,
                doc_id=f"DOC-{prefix}",
                type=EntityType.PERSON,
                surface_text=f"{prefix}_Person_{i}",
                origin=Origin.PDF_TEXT,
                identifier_trust=IdentifierTrust.NOT_APPLICABLE,
                source=SourceRef(
                    doc_id=f"DOC-{prefix}",
                    file_name=f"{prefix}.pdf",
                    file_sha256="0" * 64,
                    unit_id=f"DOC-{prefix}:p001",
                    unit_kind=UnitKind.PAGE,
                    page=1,
                    text_origin=Origin.PDF_TEXT,
                    quote=f"{prefix}_Person_{i}",
                    quote_status=QuoteStatus.VERIFIED,
                ),
            )
            mentions.append(m)

        # Store case person dict
        person = {
            "person_id": f"PER-{prefix}-01",
            "case_id": case_id,
            "cluster_id": f"CLUST-{prefix}-01",
            "canonical_name": f"{prefix} Primary Suspect",
            "name_key": f"{prefix.lower()}_primary_suspect",
            "name_variants": [f"{prefix} Primary"],
            "aliases": [],
            "attributes": {},
            "mention_ids": [m.mention_id for m in mentions],
            "identifiers": [],
            "co_occurrences": [],
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Store suggestion
        sug_id = make_suggestion_id(case_id, mentions[0].mention_id, person["person_id"])
        sug = ResolutionSuggestion(
            suggestion_id=sug_id,
            case_id=case_id,
            mention_id=mentions[0].mention_id,
            candidate_entity_id=person["person_id"],
            candidate_case_id=case_id,
            status=SuggestionStatus.CANDIDATE,
            heuristic_rank=0.9,
            rank_note="heuristic ordering, not a probability",
            signals=[],
            explanation="Test explanation",
            requires_human_decision=True,
        )

        with db_lock:
            store.store_mentions(case_id, mentions)
            store.store_case_person(person)
            store.store_suggestions(case_id, [sug])

            # Record audit action (linear hash chain requires sequential hash linking)
            action_id = make_action_id()
            latest_hash = store.get_latest_audit_hash()
            now_iso = datetime.now(UTC).isoformat()
            action = ReviewAction(
                action_id=action_id,
                case_id=case_id,
                type=ReviewActionType.APPROVE_MATCH,
                actor=f"investigator_{prefix}",
                at=now_iso,
                reason=f"Action on {case_id}",
                target_ids=[mentions[0].mention_id],
                prev_hash=latest_hash,
                entry_hash=compute_entry_hash(
                    latest_hash,
                    {
                        "action_id": action_id,
                        "case_id": case_id,
                        "type": ReviewActionType.APPROVE_MATCH.value,
                        "actor": f"investigator_{prefix}",
                        "at": now_iso,
                        "reason": f"Action on {case_id}",
                        "target_ids": [mentions[0].mention_id],
                        "payload": {},
                        "before_state": {},
                        "after_state": {},
                    },
                ),
            )
            store.record_action(action)

    # Execute both cases concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_a = executor.submit(populate_case, case_a, "ALPHA")
        f_b = executor.submit(populate_case, case_b, "BETA")
        f_a.result()
        f_b.result()

    # 1. Zero cross-contamination in case_persons
    persons_a = store.get_case_persons(case_a)
    persons_b = store.get_case_persons(case_b)

    assert len(persons_a) == 1
    assert len(persons_b) == 1
    assert persons_a[0]["case_id"] == case_a
    assert persons_b[0]["case_id"] == case_b
    assert "ALPHA" in persons_a[0]["canonical_name"]
    assert "BETA" in persons_b[0]["canonical_name"]

    # 2. Zero cross-contamination in suggestions
    sug_a = store.get_suggestions(case_a)
    sug_b = store.get_suggestions(case_b)

    assert len(sug_a) == 1
    assert len(sug_b) == 1
    assert sug_a[0]["case_id"] == case_a
    assert sug_b[0]["case_id"] == case_b

    # 3. Zero cross-contamination in audit entries
    audit_a = store.get_audit_entries(case_a)
    audit_b = store.get_audit_entries(case_b)

    assert len(audit_a) == 1
    assert len(audit_b) == 1
    assert audit_a[0]["case_id"] == case_a
    assert audit_b[0]["case_id"] == case_b

    # 4. Hash chain remains cryptographically sound across shared writes
    assert store.verify_chain() is True

    store.close()
