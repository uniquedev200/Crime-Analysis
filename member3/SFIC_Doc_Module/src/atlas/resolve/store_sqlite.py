"""SQLite entity store implementation for ATLAS Dev 3.

Implements EntityStorePort with schema tables for mentions, case_persons,
identifier_nodes, aliases, suggestions, merge_links, rejected_pairs, and audit_log.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas.contracts.enums import EntityType, IdentifierTrust
from atlas.contracts.ids import validate_case_id
from atlas.contracts.records import Mention, ResolutionSuggestion, ReviewAction
from atlas.ports.entity_store import EntityStorePort
from atlas.resolve.audit import GENESIS_HASH, canonical_json, verify_chain
from atlas.resolve.nameutils import name_key


class SqliteEntityStore(EntityStorePort):
    """SQLite implementation of EntityStorePort for cross-case entity resolution."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables and indexes."""
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS mentions (
                mention_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                type TEXT NOT NULL,
                surface_text TEXT NOT NULL,
                normalized_value TEXT,
                normalization_status TEXT,
                stated_role TEXT,
                origin TEXT NOT NULL,
                identifier_trust TEXT NOT NULL,
                confirmed_by TEXT,
                source_json TEXT NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_persons (
                person_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                cluster_id TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                name_key TEXT NOT NULL,
                name_variants_json TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                attributes_json TEXT NOT NULL,
                mention_ids_json TEXT NOT NULL,
                identifiers_json TEXT NOT NULL,
                co_occurrences_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS identifier_nodes (
                node_id TEXT PRIMARY KEY,
                identifier_type TEXT NOT NULL,
                normalized_value TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                trust TEXT NOT NULL,
                confirmed_by TEXT,
                origin TEXT NOT NULL,
                case_ids_json TEXT NOT NULL,
                mention_ids_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aliases (
                alias_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                person_id TEXT,
                primary_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                primary_name_key TEXT NOT NULL,
                alias_name_key TEXT NOT NULL,
                source_mention_id TEXT
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                suggestion_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                mention_id TEXT NOT NULL,
                candidate_entity_id TEXT NOT NULL,
                candidate_case_id TEXT,
                status TEXT NOT NULL,
                heuristic_rank REAL,
                rank_note TEXT NOT NULL,
                signals_json TEXT NOT NULL,
                explanation TEXT NOT NULL,
                requires_human_decision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS merge_links (
                link_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                entity_id_1 TEXT NOT NULL,
                entity_id_2 TEXT NOT NULL,
                action_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rejected_pairs (
                rejection_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                entity_id_1 TEXT NOT NULL,
                entity_id_2 TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                action_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL,
                actor TEXT NOT NULL,
                at TEXT NOT NULL,
                reason TEXT NOT NULL,
                target_ids_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                before_state_json TEXT,
                after_state_json TEXT,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                case_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_case_persons_case ON case_persons(case_id);
            CREATE INDEX IF NOT EXISTS idx_case_persons_name_key ON case_persons(name_key);
            CREATE INDEX IF NOT EXISTS idx_identifier_nodes_norm ON identifier_nodes(normalized_value);
            CREATE INDEX IF NOT EXISTS idx_suggestions_case ON suggestions(case_id);
            CREATE INDEX IF NOT EXISTS idx_audit_log_case ON audit_log(case_id);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        """Close database connection."""
        self._conn.close()

    def query_candidates(
        self,
        auth: Any,
        identifier_keys: list[str],
        name_keys: list[str],
        current_case_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query cross-case candidate entities matching identifiers or names, filtered by authorization."""
        allowed_cases: set[str] | None = None
        if auth is not None:
            if isinstance(auth, dict):
                raw_cases = auth.get("allowed_cases")
                if raw_cases is not None:
                    allowed_cases = set(raw_cases)
                if current_case_id is None:
                    current_case_id = auth.get("current_case") or auth.get("case_id")
            elif hasattr(auth, "allowed_cases"):
                raw_cases = auth.allowed_cases
                if raw_cases is not None:
                    allowed_cases = set(raw_cases)
                if current_case_id is None:
                    current_case_id = getattr(auth, "current_case", None) or getattr(auth, "case_id", None)

        if allowed_cases is not None and not allowed_cases:
            # Authorized for zero cases -> return empty without leaking
            return []

        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM case_persons")
        all_persons = cursor.fetchall()

        matched_candidates: list[dict[str, Any]] = []
        clean_id_keys = {str(k).strip() for k in identifier_keys if str(k).strip()}
        clean_name_keys = set()
        for k in name_keys:
            if str(k).strip():
                clean_name_keys.add(str(k).strip())
                clean_name_keys.add(name_key(str(k)))

        for row in all_persons:
            c_case_id = row["case_id"]

            # 1. Authorization check
            if allowed_cases is not None and c_case_id not in allowed_cases:
                continue

            # 2. Exclude current case
            if current_case_id is not None and c_case_id == current_case_id:
                continue

            # Parse fields
            p_dict = {
                "entity_id": row["person_id"],
                "person_id": row["person_id"],
                "case_id": c_case_id,
                "cluster_id": row["cluster_id"],
                "canonical_name": row["canonical_name"],
                "name": row["canonical_name"],
                "name_key": row["name_key"],
                "name_variants": json.loads(row["name_variants_json"]),
                "aliases": json.loads(row["aliases_json"]),
                "attributes": json.loads(row["attributes_json"]),
                "mention_ids": json.loads(row["mention_ids_json"]),
                "identifiers": json.loads(row["identifiers_json"]),
                "co_occurrences": json.loads(row["co_occurrences_json"]),
                "type": EntityType.PERSON,
            }

            matched = False

            # Match via strong/confirmed identifiers
            c_identifiers = p_dict["identifiers"]
            for ci in c_identifiers:
                trust = ci.get("trust", "")
                confirmed_by = ci.get("confirmed_by")
                # Must be strong or confirmed
                if trust == IdentifierTrust.STRONG.value or confirmed_by is not None:
                    c_norm = ci.get("normalized_value") or ci.get("value")
                    if c_norm and str(c_norm).strip() in clean_id_keys:
                        matched = True
                        break

            # Match via name_key
            if not matched and clean_name_keys:
                cand_keys = {
                    p_dict["name_key"],
                    name_key(p_dict["canonical_name"]),
                    *(alias for alias in p_dict["aliases"] if alias),
                    *(name_key(alias) for alias in p_dict["aliases"] if alias),
                }
                if cand_keys & clean_name_keys:
                    matched = True

            if matched:
                matched_candidates.append(p_dict)

        # Sort deterministically
        matched_candidates.sort(key=lambda x: str(x.get("entity_id", "")))
        return matched_candidates

    def store_mentions(self, case_id: str, mentions: list[Any]) -> None:
        """Persist extracted mentions for a case."""
        validate_case_id(case_id)
        cursor = self._conn.cursor()
        for m in mentions:
            if isinstance(m, Mention):
                m_dict = m.model_dump()
            elif isinstance(m, dict):
                m_dict = m
            else:
                continue

            mention_id = m_dict["mention_id"]
            doc_id = m_dict["doc_id"]
            m_type = m_dict["type"]
            if m_type is not None and hasattr(m_type, "value"):
                m_type = m_type.value
            surface = m_dict.get("surface_text", "")
            norm_val = m_dict.get("normalized_value")
            norm_stat = m_dict.get("normalization_status")
            if norm_stat is not None and hasattr(norm_stat, "value"):
                norm_stat = norm_stat.value
            stated_role = m_dict.get("stated_role")
            if stated_role is not None and hasattr(stated_role, "value"):
                stated_role = stated_role.value
            origin = m_dict.get("origin")
            if origin is not None and hasattr(origin, "value"):
                origin = origin.value
            id_trust = m_dict.get("identifier_trust", IdentifierTrust.NOT_APPLICABLE.value)
            if id_trust is not None and hasattr(id_trust, "value"):
                id_trust = id_trust.value
            confirmed_by = m_dict.get("confirmed_by")
            source = m_dict.get("source", {})
            if hasattr(source, "model_dump"):
                source = source.model_dump()

            cursor.execute(
                """
                INSERT OR REPLACE INTO mentions (
                    mention_id, case_id, doc_id, type, surface_text,
                    normalized_value, normalization_status, stated_role,
                    origin, identifier_trust, confirmed_by, source_json, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mention_id,
                    case_id,
                    doc_id,
                    str(m_type),
                    surface,
                    norm_val,
                    str(norm_stat) if norm_stat else None,
                    str(stated_role) if stated_role else None,
                    str(origin),
                    str(id_trust),
                    confirmed_by,
                    canonical_json(source),
                    canonical_json(m_dict),
                ),
            )
        self._conn.commit()

    def store_case_person(self, person: dict[str, Any]) -> None:
        """Insert or replace a person cluster record."""
        case_id = validate_case_id(person["case_id"])
        person_id = person["person_id"]
        cluster_id = person.get("cluster_id", person_id)
        canonical_name = person.get("canonical_name", person.get("name", ""))
        p_name_key = name_key(person.get("name_key") or canonical_name)
        now_iso = datetime.now(UTC).isoformat()

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO case_persons (
                person_id, case_id, cluster_id, canonical_name, name_key,
                name_variants_json, aliases_json, attributes_json,
                mention_ids_json, identifiers_json, co_occurrences_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person_id,
                case_id,
                cluster_id,
                canonical_name,
                p_name_key,
                canonical_json(list(person.get("name_variants", []))),
                canonical_json(list(person.get("aliases", []))),
                canonical_json(person.get("attributes", {})),
                canonical_json(list(person.get("mention_ids", []))),
                canonical_json(person.get("identifiers", [])),
                canonical_json(list(person.get("co_occurrences", []))),
                person.get("created_at", now_iso),
                now_iso,
            ),
        )
        self._conn.commit()

    def get_case_persons(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve person clusters, optionally filtered by case_id."""
        cursor = self._conn.cursor()
        if case_id is not None:
            cursor.execute("SELECT * FROM case_persons WHERE case_id = ? ORDER BY person_id", (case_id,))
        else:
            cursor.execute("SELECT * FROM case_persons ORDER BY person_id")

        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            result.append(
                {
                    "person_id": r["person_id"],
                    "entity_id": r["person_id"],
                    "case_id": r["case_id"],
                    "cluster_id": r["cluster_id"],
                    "canonical_name": r["canonical_name"],
                    "name": r["canonical_name"],
                    "name_key": r["name_key"],
                    "name_variants": json.loads(r["name_variants_json"]),
                    "aliases": json.loads(r["aliases_json"]),
                    "attributes": json.loads(r["attributes_json"]),
                    "mention_ids": json.loads(r["mention_ids_json"]),
                    "identifiers": json.loads(r["identifiers_json"]),
                    "co_occurrences": json.loads(r["co_occurrences_json"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "type": EntityType.PERSON,
                }
            )
        return result

    def get_case_person(self, person_id: str) -> dict[str, Any] | None:
        """Retrieve single person record by person_id."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM case_persons WHERE person_id = ?", (person_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "person_id": row["person_id"],
            "entity_id": row["person_id"],
            "case_id": row["case_id"],
            "cluster_id": row["cluster_id"],
            "canonical_name": row["canonical_name"],
            "name": row["canonical_name"],
            "name_key": row["name_key"],
            "name_variants": json.loads(row["name_variants_json"]),
            "aliases": json.loads(row["aliases_json"]),
            "attributes": json.loads(row["attributes_json"]),
            "mention_ids": json.loads(row["mention_ids_json"]),
            "identifiers": json.loads(row["identifiers_json"]),
            "co_occurrences": json.loads(row["co_occurrences_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "type": EntityType.PERSON,
        }

    def store_identifier_node(self, node: dict[str, Any]) -> None:
        """Insert or replace an identifier node."""
        node_id = node["node_id"]
        id_type = node.get("identifier_type", "unknown")
        norm_val = node.get("normalized_value", "")
        raw_val = node.get("raw_value", norm_val)
        trust = node.get("trust", IdentifierTrust.REVIEW_REQUIRED.value)
        if hasattr(trust, "value"):
            trust = trust.value
        confirmed_by = node.get("confirmed_by")
        origin = node.get("origin", "unknown")
        if hasattr(origin, "value"):
            origin = origin.value

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO identifier_nodes (
                node_id, identifier_type, normalized_value, raw_value,
                trust, confirmed_by, origin, case_ids_json, mention_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                str(id_type),
                norm_val,
                raw_val,
                str(trust),
                confirmed_by,
                str(origin),
                canonical_json(list(node.get("case_ids", []))),
                canonical_json(list(node.get("mention_ids", []))),
            ),
        )
        self._conn.commit()

    def get_identifier_nodes(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve identifier nodes, optionally filtering by associated case_id."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM identifier_nodes ORDER BY node_id")
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            case_ids = json.loads(r["case_ids_json"])
            if case_id is not None and case_id not in case_ids:
                continue
            result.append(
                {
                    "node_id": r["node_id"],
                    "identifier_type": r["identifier_type"],
                    "normalized_value": r["normalized_value"],
                    "raw_value": r["raw_value"],
                    "trust": r["trust"],
                    "confirmed_by": r["confirmed_by"],
                    "origin": r["origin"],
                    "case_ids": case_ids,
                    "mention_ids": json.loads(r["mention_ids_json"]),
                }
            )
        return result

    def update_mention_identifier(
        self,
        mention_id: str,
        trust: str | None = None,
        confirmed_by: str | None = None,
        normalized_value: str | None = None,
    ) -> bool:
        """Update trust, confirmation, or normalized value on a mention."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT data_json FROM mentions WHERE mention_id = ?", (mention_id,))
        row = cursor.fetchone()
        if not row:
            return False

        data = json.loads(row["data_json"])
        updates: list[str] = []
        params: list[Any] = []

        if trust is not None:
            data["identifier_trust"] = trust
            updates.append("identifier_trust = ?")
            params.append(trust)
        if confirmed_by is not None:
            data["confirmed_by"] = confirmed_by
            updates.append("confirmed_by = ?")
            params.append(confirmed_by)
        if normalized_value is not None:
            data["normalized_value"] = normalized_value
            updates.append("normalized_value = ?")
            params.append(normalized_value)

        updates.append("data_json = ?")
        params.append(canonical_json(data))
        params.append(mention_id)

        sql = f"UPDATE mentions SET {', '.join(updates)} WHERE mention_id = ?"
        cursor.execute(sql, tuple(params))
        self._conn.commit()
        return True

    def update_identifier_node(
        self,
        node_id: str,
        trust: str | None = None,
        confirmed_by: str | None = None,
        normalized_value: str | None = None,
    ) -> bool:
        """Update trust, confirmation, or normalized value on an identifier node."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT node_id FROM identifier_nodes WHERE node_id = ?", (node_id,))
        if not cursor.fetchone():
            return False

        updates: list[str] = []
        params: list[Any] = []

        if trust is not None:
            updates.append("trust = ?")
            params.append(trust)
        if confirmed_by is not None:
            updates.append("confirmed_by = ?")
            params.append(confirmed_by)
        if normalized_value is not None:
            updates.append("normalized_value = ?")
            params.append(normalized_value)

        if not updates:
            return True

        params.append(node_id)
        sql = f"UPDATE identifier_nodes SET {', '.join(updates)} WHERE node_id = ?"
        cursor.execute(sql, tuple(params))
        self._conn.commit()
        return True

    def store_alias(self, alias: dict[str, Any]) -> None:
        """Store a proven ALSO_KNOWN_AS alias link."""
        alias_id = alias["alias_id"]
        case_id = validate_case_id(alias["case_id"])
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO aliases (
                alias_id, case_id, person_id, primary_name, alias_name,
                primary_name_key, alias_name_key, source_mention_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alias_id,
                case_id,
                alias.get("person_id"),
                alias["primary_name"],
                alias["alias_name"],
                alias.get("primary_name_key", ""),
                alias.get("alias_name_key", ""),
                alias.get("source_mention_id"),
            ),
        )
        self._conn.commit()

    def get_aliases(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve alias links, optionally filtered by case_id."""
        cursor = self._conn.cursor()
        if case_id is not None:
            cursor.execute("SELECT * FROM aliases WHERE case_id = ? ORDER BY alias_id", (case_id,))
        else:
            cursor.execute("SELECT * FROM aliases ORDER BY alias_id")

        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            result.append(
                {
                    "alias_id": r["alias_id"],
                    "case_id": r["case_id"],
                    "person_id": r["person_id"],
                    "primary_name": r["primary_name"],
                    "alias_name": r["alias_name"],
                    "primary_name_key": r["primary_name_key"],
                    "alias_name_key": r["alias_name_key"],
                    "source_mention_id": r["source_mention_id"],
                }
            )
        return result

    def store_suggestions(self, case_id: str, suggestions: list[Any]) -> None:
        """Persist resolution suggestions for a case."""
        validate_case_id(case_id)
        now_iso = datetime.now(UTC).isoformat()
        cursor = self._conn.cursor()
        for s in suggestions:
            if isinstance(s, ResolutionSuggestion):
                s_dict = s.model_dump()
            elif isinstance(s, dict):
                s_dict = s
            else:
                continue

            status_val = s_dict["status"]
            if hasattr(status_val, "value"):
                status_val = status_val.value

            cursor.execute(
                """
                INSERT OR REPLACE INTO suggestions (
                    suggestion_id, case_id, mention_id, candidate_entity_id,
                    candidate_case_id, status, heuristic_rank, rank_note,
                    signals_json, explanation, requires_human_decision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s_dict["suggestion_id"],
                    case_id,
                    s_dict["mention_id"],
                    s_dict["candidate_entity_id"],
                    s_dict.get("candidate_case_id"),
                    str(status_val),
                    s_dict.get("heuristic_rank"),
                    s_dict.get("rank_note", "heuristic ordering, not a probability"),
                    canonical_json(s_dict.get("signals", [])),
                    s_dict.get("explanation", ""),
                    1 if s_dict.get("requires_human_decision", True) else 0,
                    now_iso,
                ),
            )
        self._conn.commit()

    def get_suggestions(self, case_id: str, auth: Any = None) -> list[dict[str, Any]]:
        """Retrieve suggestions for a case, filtering candidate_case_id by authorization."""
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

        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM suggestions WHERE case_id = ? ORDER BY suggestion_id", (case_id,))
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            cand_case = r["candidate_case_id"]
            if allowed_cases is not None and cand_case and cand_case not in allowed_cases:
                # Obscure candidate_case_id if unauthorized
                cand_case = None

            result.append(
                {
                    "suggestion_id": r["suggestion_id"],
                    "case_id": r["case_id"],
                    "mention_id": r["mention_id"],
                    "candidate_entity_id": r["candidate_entity_id"],
                    "candidate_case_id": cand_case,
                    "status": r["status"],
                    "heuristic_rank": r["heuristic_rank"],
                    "rank_note": r["rank_note"],
                    "signals": json.loads(r["signals_json"]),
                    "explanation": r["explanation"],
                    "requires_human_decision": bool(r["requires_human_decision"]),
                    "created_at": r["created_at"],
                }
            )
        return result

    def store_merge_link(self, link: dict[str, Any]) -> None:
        """Store an approved merge link connecting two entities."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO merge_links (
                link_id, case_id, entity_id_1, entity_id_2, action_id, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link["link_id"],
                link["case_id"],
                link["entity_id_1"],
                link["entity_id_2"],
                link["action_id"],
                link.get("status", "active"),
                link.get("created_at", datetime.now(UTC).isoformat()),
            ),
        )
        self._conn.commit()

    def get_merge_links(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve merge links, optionally filtered by case_id."""
        cursor = self._conn.cursor()
        if case_id is not None:
            cursor.execute("SELECT * FROM merge_links WHERE case_id = ? ORDER BY link_id", (case_id,))
        else:
            cursor.execute("SELECT * FROM merge_links ORDER BY link_id")
        rows = cursor.fetchall()
        return [
            {
                "link_id": r["link_id"],
                "case_id": r["case_id"],
                "entity_id_1": r["entity_id_1"],
                "entity_id_2": r["entity_id_2"],
                "action_id": r["action_id"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def store_rejected_pair(self, rejection: dict[str, Any]) -> None:
        """Store a rejected match pair with evidence fingerprint."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO rejected_pairs (
                rejection_id, case_id, entity_id_1, entity_id_2, fingerprint, action_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rejection["rejection_id"],
                rejection["case_id"],
                rejection["entity_id_1"],
                rejection["entity_id_2"],
                rejection["fingerprint"],
                rejection["action_id"],
                rejection.get("created_at", datetime.now(UTC).isoformat()),
            ),
        )
        self._conn.commit()

    def get_rejected_pairs(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve rejected pairs with evidence fingerprints."""
        cursor = self._conn.cursor()
        if case_id is not None:
            cursor.execute("SELECT * FROM rejected_pairs WHERE case_id = ? ORDER BY rejection_id", (case_id,))
        else:
            cursor.execute("SELECT * FROM rejected_pairs ORDER BY rejection_id")
        rows = cursor.fetchall()
        return [
            {
                "rejection_id": r["rejection_id"],
                "case_id": r["case_id"],
                "entity_id_1": r["entity_id_1"],
                "entity_id_2": r["entity_id_2"],
                "fingerprint": r["fingerprint"],
                "action_id": r["action_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_latest_audit_hash(self) -> str:
        """Return entry_hash of the latest audit row, or GENESIS_HASH if empty."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT entry_hash FROM audit_log ORDER BY entry_id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return str(row["entry_hash"])
        return GENESIS_HASH

    def record_action(self, action: Any) -> None:
        """Append an audited review action to the append-only audit_log table."""
        if isinstance(action, ReviewAction):
            a_dict = action.model_dump()
        elif isinstance(action, dict):
            a_dict = action
        else:
            raise TypeError(f"Expected ReviewAction or dict, got {type(action).__name__}")

        action_id = a_dict["action_id"]
        a_type = a_dict["type"]
        if hasattr(a_type, "value"):
            a_type = a_type.value
        actor = a_dict["actor"]
        at_ts = a_dict["at"]
        reason = a_dict["reason"]
        target_ids = sorted(a_dict.get("target_ids") or [])
        payload = a_dict.get("payload") or {}
        before_state = a_dict.get("before_state")
        after_state = a_dict.get("after_state")
        prev_hash = a_dict.get("prev_hash", GENESIS_HASH)
        entry_hash = a_dict["entry_hash"]
        case_id = a_dict.get("case_id")

        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_log (
                action_id, type, actor, at, reason, target_ids_json,
                payload_json, before_state_json, after_state_json,
                prev_hash, entry_hash, case_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                str(a_type),
                actor,
                at_ts,
                reason,
                canonical_json(target_ids),
                canonical_json(payload),
                canonical_json(before_state) if before_state is not None else None,
                canonical_json(after_state) if after_state is not None else None,
                prev_hash,
                entry_hash,
                case_id,
            ),
        )
        self._conn.commit()

    def get_audit_entries(self, case_id: str | None = None) -> list[dict[str, Any]]:
        """Return list of audit log entries in append-only sequential order."""
        cursor = self._conn.cursor()
        if case_id is not None:
            cursor.execute("SELECT * FROM audit_log WHERE case_id = ? ORDER BY entry_id ASC", (case_id,))
        else:
            cursor.execute("SELECT * FROM audit_log ORDER BY entry_id ASC")

        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            before_json = r["before_state_json"]
            after_json = r["after_state_json"]
            result.append(
                {
                    "entry_id": r["entry_id"],
                    "action_id": r["action_id"],
                    "type": r["type"],
                    "actor": r["actor"],
                    "at": r["at"],
                    "reason": r["reason"],
                    "target_ids": json.loads(r["target_ids_json"]),
                    "payload": json.loads(r["payload_json"]),
                    "before_state": json.loads(before_json) if before_json else None,
                    "after_state": json.loads(after_json) if after_json else None,
                    "prev_hash": r["prev_hash"],
                    "entry_hash": r["entry_hash"],
                    "case_id": r["case_id"],
                }
            )
        return result

    def verify_chain(self) -> bool:
        """Verify cryptographic integrity of the hash-chained audit log."""
        return verify_chain(self)


__all__ = ["SqliteEntityStore"]
