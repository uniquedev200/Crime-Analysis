"""Contradiction detection for within-document and within-case entity clusters.

Implements Section 5.6 Contradiction specifications:
- Identifies conflicting attributes within a person cluster:
  - Differing DOB values
  - Differing father_name values (compared via name_key)
  - Differing age values beyond +/- 2 years tolerance
- Emits actionable 'contradiction' ReviewItem records holding all conflicting values and sources.
- Never picks or suppresses conflicting values.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from atlas.contracts.enums import AttrName, ReviewKind
from atlas.contracts.ids import make_review_id
from atlas.contracts.records import Mention, ReviewItem, SourceRef
from atlas.normalize.names import name_key

_AGE_NUMERIC_RE = re.compile(r"\b(\d{1,3})\b")


def extract_numeric_age(value_text: str) -> int | None:
    """Extract numeric integer age from attribute text string (e.g. '32 yrs' -> 32)."""
    match = _AGE_NUMERIC_RE.search(value_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def detect_contradictions(
    mentions: Sequence[Mention],
    case_id: str,
    target_ids: list[str] | None = None,
) -> list[ReviewItem]:
    """Detect attribute contradictions among a set of mentions belonging to the same cluster.

    Checks:
    1. dob: Any distinct dates.
    2. father_name: Differing father names evaluated using name_key.
    3. age: Numeric ages with difference > 2 years.

    Args:
        mentions: Sequence of Mention objects in the local cluster.
        case_id: Active case identifier.
        target_ids: Optional list of target entity / mention IDs. Defaults to mention_ids.

    Returns:
        List of generated ReviewItem objects with kind=ReviewKind.CONTRADICTION.
    """
    review_items: list[ReviewItem] = []
    effective_targets = target_ids if target_ids is not None else [m.mention_id for m in mentions]

    # Collect attributes with their source references and parent mention IDs
    dob_entries: list[dict[str, Any]] = []
    father_entries: list[dict[str, Any]] = []
    age_entries: list[dict[str, Any]] = []

    for m in mentions:
        for attr in m.attributes:
            src = attr.source or m.source
            if attr.name == AttrName.DOB:
                dob_entries.append(
                    {
                        "mention_id": m.mention_id,
                        "value": attr.value_text.strip(),
                        "source": src,
                    }
                )
            elif attr.name == AttrName.FATHER_NAME:
                father_entries.append(
                    {
                        "mention_id": m.mention_id,
                        "value": attr.value_text.strip(),
                        "key": name_key(attr.value_text.strip()),
                        "source": src,
                    }
                )
            elif attr.name == AttrName.AGE:
                num_age = extract_numeric_age(attr.value_text)
                age_entries.append(
                    {
                        "mention_id": m.mention_id,
                        "value": attr.value_text.strip(),
                        "numeric_age": num_age,
                        "source": src,
                    }
                )

    # 1. Check DOB contradictions
    distinct_dobs: dict[str, list[SourceRef]] = {}
    for entry in dob_entries:
        v = entry["value"].lower()
        if v not in distinct_dobs:
            distinct_dobs[v] = []
        if entry["source"]:
            distinct_dobs[v].append(entry["source"])

    if len(distinct_dobs) > 1:
        details = []
        for val, srcs in distinct_dobs.items():
            src_quotes = [f"'{s.quote}' ({s.unit_id})" for s in srcs]
            details.append(f"value '{val}' from {', '.join(src_quotes)}")
        detail_msg = f"Contradicting dob values found: {'; '.join(details)}"
        t_id = effective_targets[0] if effective_targets else "cluster"
        rev_id = make_review_id(case_id, ReviewKind.CONTRADICTION.value, t_id, detail_msg)
        review_items.append(
            ReviewItem(
                review_id=rev_id,
                case_id=case_id,
                kind=ReviewKind.CONTRADICTION,
                target_ids=list(effective_targets),
                detail=detail_msg,
            )
        )

    # 2. Check Father Name contradictions
    distinct_fathers: dict[str, tuple[str, list[SourceRef]]] = {}
    for entry in father_entries:
        k = entry["key"]
        if not k:
            continue
        if k not in distinct_fathers:
            distinct_fathers[k] = (entry["value"], [])
        if entry["source"]:
            distinct_fathers[k][1].append(entry["source"])

    if len(distinct_fathers) > 1:
        details = []
        for _k, (raw_val, srcs) in distinct_fathers.items():
            src_quotes = [f"'{s.quote}' ({s.unit_id})" for s in srcs]
            details.append(f"value '{raw_val}' from {', '.join(src_quotes)}")
        detail_msg = f"Contradicting father_name values found: {'; '.join(details)}"
        t_id = effective_targets[0] if effective_targets else "cluster"
        rev_id = make_review_id(case_id, ReviewKind.CONTRADICTION.value, t_id, detail_msg)
        review_items.append(
            ReviewItem(
                review_id=rev_id,
                case_id=case_id,
                kind=ReviewKind.CONTRADICTION,
                target_ids=list(effective_targets),
                detail=detail_msg,
            )
        )

    # 3. Check Age contradictions (beyond +/- 2 years tolerance)
    valid_ages = [e for e in age_entries if e["numeric_age"] is not None]
    if valid_ages:
        num_vals = [e["numeric_age"] for e in valid_ages if e["numeric_age"] is not None]
        if num_vals and (max(num_vals) - min(num_vals) > 2):
            details = []
            for entry in valid_ages:
                src = entry["source"]
                src_quote = f"'{src.quote}' ({src.unit_id})" if src else "unknown"
                details.append(f"value '{entry['value']}' ({entry['numeric_age']} yrs) from {src_quote}")
            detail_msg = f"Contradicting age values (> 2 years tolerance): {'; '.join(details)}"
            t_id = effective_targets[0] if effective_targets else "cluster"
            rev_id = make_review_id(case_id, ReviewKind.CONTRADICTION.value, t_id, detail_msg)
            review_items.append(
                ReviewItem(
                    review_id=rev_id,
                    case_id=case_id,
                    kind=ReviewKind.CONTRADICTION,
                    target_ids=list(effective_targets),
                    detail=detail_msg,
                )
            )

    return review_items


__all__ = ["detect_contradictions", "extract_numeric_age"]
