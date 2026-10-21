"""Signal extraction and deterministic heuristic ranking for entity resolution.

Compares mentions and candidate entities across cases, extracting supporting
and contradicting signals, and computes a heuristic ordering rank in [0.0, 1.0].
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Final

import yaml

from atlas.contracts.enums import EntityType, IdentifierTrust, SignalPolarity
from atlas.contracts.records import Signal, SourceRef
from atlas.resolve.nameutils import are_names_compatible, name_similarity_scores

RANK_NOTE: Final[str] = "heuristic ordering, not a probability"

_DEFAULT_WEIGHTS: Final[dict[str, float]] = {
    "exact_identifier": 1.0,
    "name_similarity": 0.4,
    "parent_name": 0.3,
    "age_dob_compat": 0.2,
    "address_overlap": 0.15,
    "co_occurrence": 0.25,
    "alias_stated": 0.5,
    "MIN_RANK": 0.3,
    "T_NAME_HIGH": 0.85,
    "RANK_EPSILON": 0.05,
    "MAX_SCORE": 2.0,
    "CONTRADICTION_PENALTY": 0.3,
}

_WEIGHTS_CACHE: dict[str, float] | None = None


def load_resolver_weights(config_path: Path | str | None = None) -> dict[str, float]:
    """Load resolver weights from YAML configuration file with fallback to defaults."""
    global _WEIGHTS_CACHE
    if _WEIGHTS_CACHE is not None and config_path is None:
        return _WEIGHTS_CACHE

    if config_path is None:
        # Look in workspace root config/
        candidate_path = Path("config/resolver_weights.yaml")
        if not candidate_path.exists():
            candidate_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "resolver_weights.yaml"
    else:
        candidate_path = Path(config_path)

    weights = dict(_DEFAULT_WEIGHTS)
    if candidate_path.exists():
        import contextlib

        with contextlib.suppress(Exception), open(candidate_path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    with contextlib.suppress(ValueError, TypeError):
                        weights[k] = float(v)

    if config_path is None:
        _WEIGHTS_CACHE = weights
    return weights


def _clean_token_set(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens of length >= 3."""
    tokens = re.findall(r"[a-zA-Z0-9]{3,}", text.lower())
    return set(tokens)


def _extract_identifiers(entity_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract identifier entries with trust and confirmation status."""
    raw_ids = entity_dict.get("identifiers", [])
    result: list[dict[str, Any]] = []
    for item in raw_ids:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            result.append({"type": "unknown", "value": item, "trust": "strong"})
    return result


def _is_identifier_eligible(ident: dict[str, Any]) -> bool:
    """Return True if identifier is strong or confirmed by a human reviewer."""
    trust = ident.get("trust", "")
    if isinstance(trust, IdentifierTrust):
        trust = trust.value
    confirmed_by = ident.get("confirmed_by")
    if trust == IdentifierTrust.STRONG.value:
        return True
    return bool(confirmed_by is not None and str(confirmed_by).strip())


def _parse_age(val: Any) -> int | None:
    """Parse integer age from string or number."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    match = re.search(r"\b(\d{1,3})\b", str(val))
    if match:
        return int(match.group(1))
    return None


def extract_signals(
    mention_or_entity: dict[str, Any],
    candidate_entity: dict[str, Any],
    known_aliases: list[dict[str, Any]] | None = None,
) -> list[Signal]:
    """Compare a mention or person cluster against a candidate entity and extract signals."""
    signals: list[Signal] = []

    # 1. Entity type compatibility
    m_type = mention_or_entity.get("type", EntityType.PERSON)
    c_type = candidate_entity.get("type", EntityType.PERSON)
    if isinstance(m_type, EntityType):
        m_type = m_type.value
    if isinstance(c_type, EntityType):
        c_type = c_type.value

    if m_type != c_type:
        signals.append(
            Signal(
                kind="incompatible_entity_type",
                polarity=SignalPolarity.CONTRADICTS,
                detail=f"Incompatible entity types: {m_type} vs {c_type}",
                sources=[],
            )
        )
        return signals

    # 2. Exact identifier match
    m_ids = _extract_identifiers(mention_or_entity)
    c_ids = _extract_identifiers(candidate_entity)

    # Filter to eligible identifiers (strong or confirmed)
    eligible_m_ids = [i for i in m_ids if _is_identifier_eligible(i)]
    eligible_c_ids = [i for i in c_ids if _is_identifier_eligible(i)]

    shared_identifiers: list[str] = []
    id_sources: list[SourceRef] = []
    for mi in eligible_m_ids:
        m_val = mi.get("normalized_value") or mi.get("value")
        if not m_val:
            continue
        for ci in eligible_c_ids:
            c_val = ci.get("normalized_value") or ci.get("value")
            if c_val and str(m_val).strip() == str(c_val).strip():
                shared_identifiers.append(f"{mi.get('type', 'id')}:{m_val}")
                for src in (mi.get("source"), ci.get("source")):
                    if isinstance(src, SourceRef) and src not in id_sources:
                        id_sources.append(src)

    if shared_identifiers:
        signals.append(
            Signal(
                kind="exact_identifier",
                polarity=SignalPolarity.SUPPORTS,
                detail=f"Shared strong identifier(s): {', '.join(sorted(set(shared_identifiers)))}",
                sources=id_sources,
            )
        )

    # 3. Name similarity
    m_name = (
        mention_or_entity.get("canonical_name")
        or mention_or_entity.get("name")
        or mention_or_entity.get("surface_text", "")
    )
    c_name = (
        candidate_entity.get("canonical_name")
        or candidate_entity.get("name")
        or candidate_entity.get("surface_text", "")
    )

    all_m_names = [
        m_name,
        *list(mention_or_entity.get("name_variants", [])),
    ]
    all_c_names = [
        c_name,
        *list(candidate_entity.get("name_variants", [])),
    ]
    all_m_names = [n for n in all_m_names if n]
    all_c_names = [n for n in all_c_names if n]

    best_sim = 0.0
    best_tsr = 0.0
    best_jw = 0.0
    for n1 in all_m_names:
        for n2 in all_c_names:
            scores = name_similarity_scores(n1, n2)
            if scores["composite"] > best_sim:
                best_sim = scores["composite"]
                best_tsr = scores["token_sort_ratio"]
                best_jw = scores["jaro_winkler"]

    name_sources: list[SourceRef] = []
    for src in (mention_or_entity.get("source"), candidate_entity.get("source")):
        if isinstance(src, SourceRef):
            name_sources.append(src)

    signals.append(
        Signal(
            kind="name_similarity",
            polarity=SignalPolarity.SUPPORTS,
            detail=(
                f"Similarity: {best_sim:.3f} "
                f"(token_sort_ratio={best_tsr:.2f}, jaro_winkler={best_jw:.2f}) "
                f"comparing '{m_name}' to '{c_name}'"
            ),
            sources=name_sources,
        )
    )

    # 4. Stated alias link (ALSO_KNOWN_AS)
    alias_match_found = False
    m_aliases = set(mention_or_entity.get("aliases", []))
    c_aliases = set(candidate_entity.get("aliases", []))
    if known_aliases:
        for ak in known_aliases:
            p_name = ak.get("primary_name", "")
            a_name = ak.get("alias_name", "")
            if (are_names_compatible(p_name, m_name) and are_names_compatible(a_name, c_name)) or (
                are_names_compatible(p_name, c_name) and are_names_compatible(a_name, m_name)
            ):
                alias_match_found = True

    for a in m_aliases:
        if are_names_compatible(a, c_name):
            alias_match_found = True
    for a in c_aliases:
        if are_names_compatible(a, m_name):
            alias_match_found = True

    if alias_match_found:
        signals.append(
            Signal(
                kind="alias_stated",
                polarity=SignalPolarity.SUPPORTS,
                detail=f"Stated or confirmed alias link between '{m_name}' and '{c_name}'",
                sources=[],
            )
        )

    # Attributes comparison (father_name, age, dob, address)
    m_attrs = mention_or_entity.get("attributes", {})
    if isinstance(m_attrs, list):
        m_attrs = {
            a.get("name") if isinstance(a, dict) else getattr(a, "name", ""): a.get("value_text")
            if isinstance(a, dict)
            else getattr(a, "value_text", "")
            for a in m_attrs
        }
    c_attrs = candidate_entity.get("attributes", {})
    if isinstance(c_attrs, list):
        c_attrs = {
            a.get("name") if isinstance(a, dict) else getattr(a, "name", ""): a.get("value_text")
            if isinstance(a, dict)
            else getattr(a, "value_text", "")
            for a in c_attrs
        }

    # 5. Parent / Father Name
    m_father = m_attrs.get("father_name") or mention_or_entity.get("father_name")
    c_father = c_attrs.get("father_name") or candidate_entity.get("father_name")
    if m_father and c_father:
        father_sim = name_similarity_scores(str(m_father), str(c_father))["composite"]
        if father_sim >= 0.80:
            signals.append(
                Signal(
                    kind="parent_name",
                    polarity=SignalPolarity.SUPPORTS,
                    detail=f"Matching parent name: '{m_father}' vs '{c_father}' ({father_sim:.2f})",
                    sources=[],
                )
            )
        elif father_sim < 0.60:
            signals.append(
                Signal(
                    kind="parent_name_conflict",
                    polarity=SignalPolarity.CONTRADICTS,
                    detail=f"Conflicting parent name: '{m_father}' vs '{c_father}' ({father_sim:.2f})",
                    sources=[],
                )
            )

    # 6. Age and DOB compatibility
    m_dob = m_attrs.get("dob") or mention_or_entity.get("dob")
    c_dob = c_attrs.get("dob") or candidate_entity.get("dob")
    m_age = _parse_age(m_attrs.get("age") or mention_or_entity.get("age"))
    c_age = _parse_age(c_attrs.get("age") or candidate_entity.get("age"))

    if m_dob and c_dob:
        if str(m_dob).strip() == str(c_dob).strip():
            signals.append(
                Signal(
                    kind="age_dob_compat",
                    polarity=SignalPolarity.SUPPORTS,
                    detail=f"Matching date of birth: '{m_dob}'",
                    sources=[],
                )
            )
        else:
            signals.append(
                Signal(
                    kind="dob_conflict",
                    polarity=SignalPolarity.CONTRADICTS,
                    detail=f"Conflicting date of birth: '{m_dob}' vs '{c_dob}'",
                    sources=[],
                )
            )
    elif m_age is not None and c_age is not None:
        age_diff = abs(m_age - c_age)
        if age_diff <= 2:
            signals.append(
                Signal(
                    kind="age_dob_compat",
                    polarity=SignalPolarity.SUPPORTS,
                    detail=f"Compatible ages: {m_age} and {c_age} (diff={age_diff} <= 2)",
                    sources=[],
                )
            )
        else:
            signals.append(
                Signal(
                    kind="dob_conflict",
                    polarity=SignalPolarity.CONTRADICTS,
                    detail=f"Conflicting ages: {m_age} vs {c_age} (diff={age_diff} > 2)",
                    sources=[],
                )
            )

    # 7. Address overlap
    m_addr = m_attrs.get("address") or mention_or_entity.get("address")
    c_addr = c_attrs.get("address") or candidate_entity.get("address")
    if m_addr and c_addr:
        toks1 = _clean_token_set(str(m_addr))
        toks2 = _clean_token_set(str(c_addr))
        if toks1 and toks2:
            intersection = toks1 & toks2
            union = toks1 | toks2
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard >= 0.30 or len(intersection) >= 3:
                signals.append(
                    Signal(
                        kind="address_overlap",
                        polarity=SignalPolarity.SUPPORTS,
                        detail=f"Address overlap: tokens={len(intersection)}, jaccard={jaccard:.2f}",
                        sources=[],
                    )
                )

    # 8. Co-occurrence
    m_co = set(mention_or_entity.get("co_occurrences", []))
    c_co = set(candidate_entity.get("co_occurrences", []))
    shared_co = m_co & c_co
    if shared_co:
        signals.append(
            Signal(
                kind="co_occurrence",
                polarity=SignalPolarity.SUPPORTS,
                detail=f"Co-occurring elements: {', '.join(sorted(shared_co))}",
                sources=[],
            )
        )

    return signals


def compute_heuristic_rank(
    signals: list[Signal],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute deterministic heuristic ordering score in [0.0, 1.0]."""
    if weights is None:
        weights = load_resolver_weights()

    max_score = weights.get("MAX_SCORE", 2.0)
    penalty_weight = weights.get("CONTRADICTION_PENALTY", 0.3)

    pos_score = 0.0
    penalty = 0.0

    for s in signals:
        if s.polarity == SignalPolarity.CONTRADICTS:
            penalty += penalty_weight
        elif s.polarity == SignalPolarity.SUPPORTS:
            w = weights.get(s.kind, 0.0)
            if s.kind == "name_similarity":
                # Parse similarity score from detail
                match = re.search(r"Similarity:\s*([0-9.]+)", s.detail)
                sim_factor = float(match.group(1)) if match else 1.0
                pos_score += w * sim_factor
            else:
                pos_score += w

    net_score = max(0.0, pos_score - penalty)
    rank = min(1.0, max(0.0, net_score / max_score))
    return round(rank, 4)


def compute_signal_fingerprint(signals: list[Signal]) -> str:
    """Compute deterministic SHA-256 fingerprint for a list of signals."""
    tokens = sorted(f"{s.kind}:{s.polarity.value}:{s.detail}" for s in signals)
    raw = ";".join(tokens).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def has_new_evidence(old_fingerprint: str, new_signals: list[Signal]) -> bool:
    """Return True if new signals represent different or expanded evidence."""
    new_fp = compute_signal_fingerprint(new_signals)
    return new_fp != old_fingerprint


__all__ = [
    "RANK_NOTE",
    "compute_heuristic_rank",
    "compute_signal_fingerprint",
    "extract_signals",
    "has_new_evidence",
    "load_resolver_weights",
]
