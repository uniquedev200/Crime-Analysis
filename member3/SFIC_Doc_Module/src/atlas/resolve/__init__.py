"""ATLAS cross-case entity resolution, audit logging, and human review module.

Provides SqliteEntityStore, signal extraction, deterministic heuristic ranking,
candidate matching, review action processing, and hash chain verification.
"""

from __future__ import annotations

from atlas.resolve.audit import (
    GENESIS_HASH,
    canonical_json,
    compute_entry_hash,
    get_canonical_action_payload,
    verify_chain,
)
from atlas.resolve.candidates import generate_suggestions
from atlas.resolve.nameutils import (
    are_names_compatible,
    clean_name,
    get_name_tokens,
    is_initials_compatible,
    name_key,
    name_similarity_scores,
)
from atlas.resolve.review import apply_review_action
from atlas.resolve.signals import (
    RANK_NOTE,
    compute_heuristic_rank,
    compute_signal_fingerprint,
    extract_signals,
    has_new_evidence,
    load_resolver_weights,
)
from atlas.resolve.store_sqlite import SqliteEntityStore

__all__ = [
    "GENESIS_HASH",
    "RANK_NOTE",
    "SqliteEntityStore",
    "apply_review_action",
    "are_names_compatible",
    "canonical_json",
    "clean_name",
    "compute_entry_hash",
    "compute_heuristic_rank",
    "compute_signal_fingerprint",
    "extract_signals",
    "generate_suggestions",
    "get_canonical_action_payload",
    "get_name_tokens",
    "has_new_evidence",
    "is_initials_compatible",
    "load_resolver_weights",
    "name_key",
    "name_similarity_scores",
    "verify_chain",
]
