"""Candidate generation and suggestion status assignment for entity resolution.

Implements Section 5.10 deterministic status rules:
- no_match: rank < MIN_RANK
- candidate: exact identifier + name_similarity >= T_NAME_HIGH + no contradictions + single top candidate
- needs_review: exact identifier with dissimilar names (shared/reassigned number or alias) OR name-only with corroboration
- ambiguous: >= 2 candidates within RANK_EPSILON, same name with differing attributes, or any contradiction
- Name-only without corroborating signal: no suggestion emitted
- Incompatible entity types never match
- requires_human_decision = True always
- Rejected pairs suppressed unless new evidence appears
- RESOLVER NEVER CALLS WRITE ON CANONICAL ENTITIES
"""

from __future__ import annotations

import re
from typing import Any

from atlas.contracts.enums import IdentifierTrust, SignalPolarity, SuggestionStatus
from atlas.contracts.ids import make_suggestion_id
from atlas.contracts.records import ResolutionSuggestion
from atlas.resolve.nameutils import name_key
from atlas.resolve.signals import (
    RANK_NOTE,
    compute_heuristic_rank,
    extract_signals,
    has_new_evidence,
    load_resolver_weights,
)
from atlas.resolve.store_sqlite import SqliteEntityStore


def _is_eligible_identifier(ident: dict[str, Any]) -> bool:
    """Return True if identifier is strong or has been confirmed by a reviewer."""
    trust = ident.get("trust", "")
    if hasattr(trust, "value"):
        trust = trust.value
    confirmed_by = ident.get("confirmed_by")
    if trust == IdentifierTrust.STRONG.value:
        return True
    return bool(confirmed_by is not None and str(confirmed_by).strip())


def _extract_keys(person: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Extract eligible identifier keys and name keys for querying candidate entities."""
    name_keys: list[str] = []
    p_name = person.get("canonical_name") or person.get("name") or person.get("surface_text", "")
    if p_name:
        name_keys.append(name_key(p_name))

    for a in person.get("aliases", []):
        if a:
            name_keys.append(name_key(a))
    for v in person.get("name_variants", []):
        if v:
            name_keys.append(name_key(v))

    identifier_keys: list[str] = []
    raw_ids = person.get("identifiers", [])
    for item in raw_ids:
        if isinstance(item, dict):
            if _is_eligible_identifier(item):
                val = item.get("normalized_value") or item.get("value")
                if val:
                    identifier_keys.append(str(val).strip())
        elif isinstance(item, str) and item.strip():
            identifier_keys.append(item.strip())

    return sorted(set(identifier_keys)), sorted(set(name_keys))


def generate_suggestions(
    store: SqliteEntityStore,
    current_case_id: str,
    new_persons: list[dict[str, Any]],
    auth: Any = None,
) -> list[ResolutionSuggestion]:
    """Generate cross-case resolution suggestions without writing to canonical entities.

    This function is strictly read-only with respect to canonical entity storage.
    """
    weights = load_resolver_weights()
    min_rank = weights.get("MIN_RANK", 0.3)
    t_name_high = weights.get("T_NAME_HIGH", 0.85)
    rank_epsilon = weights.get("RANK_EPSILON", 0.05)

    all_suggestions: list[ResolutionSuggestion] = []
    rejected_pairs = store.get_rejected_pairs()
    known_aliases = store.get_aliases()

    for person in new_persons:
        person_id = person.get("person_id") or person.get("entity_id") or person.get("cluster_id", "")
        mention_id = person.get("mention_id") or (
            person.get("mention_ids", [person_id])[0] if person.get("mention_ids") else person_id
        )

        id_keys, n_keys = _extract_keys(person)
        if not id_keys and not n_keys:
            continue

        # Strictly cross-case query: query_candidates excludes current_case_id and unauthorized cases
        candidates = store.query_candidates(
            auth=auth,
            identifier_keys=id_keys,
            name_keys=n_keys,
            current_case_id=current_case_id,
        )

        scored_candidates: list[dict[str, Any]] = []

        for cand in candidates:
            cand_id = cand["entity_id"]

            signals = extract_signals(person, cand, known_aliases=known_aliases)

            # Incompatible entity types never match
            if any(s.kind == "incompatible_entity_type" for s in signals):
                continue

            # Check rejected pairs suppression
            suppressed = False
            for rej in rejected_pairs:
                if (rej["entity_id_1"] == person_id and rej["entity_id_2"] == cand_id) or (
                    rej["entity_id_1"] == cand_id and rej["entity_id_2"] == person_id
                ):
                    old_fp = rej["fingerprint"]
                    if not has_new_evidence(old_fp, signals):
                        suppressed = True
                        break
            if suppressed:
                continue

            rank = compute_heuristic_rank(signals, weights)

            has_contradiction = any(s.polarity == SignalPolarity.CONTRADICTS for s in signals)
            has_exact_identifier = any(s.kind == "exact_identifier" for s in signals)
            has_corroboration = any(
                s.kind in ("parent_name", "age_dob_compat", "address_overlap", "co_occurrence", "alias_stated")
                for s in signals
                if s.polarity == SignalPolarity.SUPPORTS
            )

            # Name similarity calculation
            name_sim = 0.0
            for s in signals:
                if s.kind == "name_similarity":
                    match = re.search(r"Similarity:\s*([0-9.]+)", s.detail)
                    if match:
                        name_sim = float(match.group(1))

            # Rule: Name-only without corroborating signal: no suggestion emitted
            if not has_exact_identifier and not has_corroboration:
                continue

            # Rule: rank < MIN_RANK -> no match
            if rank < min_rank:
                continue

            scored_candidates.append(
                {
                    "candidate": cand,
                    "signals": signals,
                    "rank": rank,
                    "name_sim": name_sim,
                    "has_contradiction": has_contradiction,
                    "has_exact_identifier": has_exact_identifier,
                    "has_corroboration": has_corroboration,
                }
            )

        if not scored_candidates:
            continue

        # Sort candidates by rank descending
        scored_candidates.sort(key=lambda x: (x["rank"], x["name_sim"]), reverse=True)

        # Check for ambiguity conditions across candidates:
        # Condition 1: Multiple candidates within RANK_EPSILON
        multiple_within_epsilon = False
        if len(scored_candidates) >= 2:
            top_rank = scored_candidates[0]["rank"]
            second_rank = scored_candidates[1]["rank"]
            if abs(top_rank - second_rank) <= rank_epsilon:
                multiple_within_epsilon = True

        # Condition 2: Multiple candidates with same name but differing attributes
        multiple_same_name_diff_attrs = False
        if len(scored_candidates) >= 2:
            cand_names = [c["candidate"].get("canonical_name", "").strip().lower() for c in scored_candidates]
            if len(cand_names) != len(set(cand_names)):
                multiple_same_name_diff_attrs = True

        # Determine suggestion status for each candidate
        for idx, item in enumerate(scored_candidates):
            cand = item["candidate"]
            signals = item["signals"]
            rank = item["rank"]
            name_sim = item["name_sim"]
            has_contradiction = item["has_contradiction"]
            has_exact_id = item["has_exact_identifier"]

            status = SuggestionStatus.NEEDS_REVIEW
            explanation = ""

            if has_contradiction:
                status = SuggestionStatus.AMBIGUOUS
                conflicts = [s.detail for s in signals if s.polarity == SignalPolarity.CONTRADICTS]
                explanation = f"Match is ambiguous due to conflicting attributes: {'; '.join(conflicts)}."

            elif multiple_within_epsilon and idx < 2:
                status = SuggestionStatus.AMBIGUOUS
                explanation = (
                    f"Ambiguous match: multiple candidates with close ranking scores within epsilon ({rank_epsilon})."
                )

            elif multiple_same_name_diff_attrs:
                status = SuggestionStatus.AMBIGUOUS
                explanation = (
                    "Ambiguous match: multiple candidates with same name but differing demographic attributes."
                )

            elif has_exact_id:
                if name_sim >= t_name_high and not has_contradiction and idx == 0 and not multiple_within_epsilon:
                    status = SuggestionStatus.CANDIDATE
                    explanation = (
                        f"Exact strong identifier match with high name similarity ({name_sim:.2f} >= {t_name_high})."
                    )
                else:
                    status = SuggestionStatus.NEEDS_REVIEW
                    explanation = (
                        "Exact identifier matches, but names are dissimilar. "
                        "Possible shared family phone, reassigned number, or unconfirmed alias."
                    )

            else:
                # Name-only with corroboration
                status = SuggestionStatus.NEEDS_REVIEW
                explanation = (
                    "Name matches with corroborating demographic or co-occurrence signal, "
                    "but no shared strong identifier."
                )

            sug_id = make_suggestion_id(current_case_id, mention_id, cand["entity_id"])
            sug = ResolutionSuggestion(
                suggestion_id=sug_id,
                case_id=current_case_id,
                mention_id=mention_id,
                candidate_entity_id=cand["entity_id"],
                candidate_case_id=cand["case_id"],
                status=status,
                heuristic_rank=rank,
                rank_note=RANK_NOTE,
                signals=signals,
                explanation=explanation,
                requires_human_decision=True,
            )
            all_suggestions.append(sug)

    return all_suggestions


__all__ = ["generate_suggestions"]
