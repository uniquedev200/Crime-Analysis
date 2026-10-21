"""Within-document consolidation and local person clustering.

Implements Section 5.6 specifications:
1. Deduplication of model items across chunks by (type, normalized_or_surface, unit_id, quote).
2. Preservation and merging of all SourceRef provenance without dropping sources.
3. Person clustering within a document:
   - Mentions merge only if identical name_key and no contradicting attributes (dob, father_name, age).
   - Stated ALSO_KNOWN_AS relationships link alias forms.
   - Two same-name people with contradicting attributes stay separate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from atlas.consolidate.contradictions import detect_contradictions, extract_numeric_age
from atlas.contracts.enums import AttrName, EntityType, RelType
from atlas.contracts.records import Event, Mention, MentionAttribute, Relationship, ReviewItem, SourceRef
from atlas.normalize.names import name_key
from atlas.provenance.normalize_text import normalize_for_match


@dataclass
class LocalPersonCluster:
    """Cluster of co-referent PERSON mentions within a single evidence document."""

    cluster_id: str
    case_id: str
    doc_id: str
    canonical_name: str
    name_keys: set[str] = field(default_factory=set)
    mention_ids: list[str] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    attributes: list[MentionAttribute] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)


def deduplicate_mentions(mentions: Sequence[Mention]) -> list[Mention]:
    """Deduplicate extracted mentions across chunks by (type, normalized_or_surface, unit_id, quote).

    Merges source occurrence counts and unions attributes and review flags.
    """
    grouped: dict[tuple[str, str, str, str], list[Mention]] = {}

    for m in mentions:
        norm_val = m.normalized_value if m.normalized_value is not None else m.surface_text
        norm_quote = normalize_for_match(m.source.quote)
        key = (m.type.value, norm_val, m.source.unit_id, norm_quote)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(m)

    deduped: list[Mention] = []

    for group in grouped.values():
        primary = group[0]
        if len(group) == 1:
            deduped.append(primary)
            continue

        # Merge occurrence counts
        total_occurrences = sum(item.source.occurrence_count for item in group)

        # Merge attributes avoiding exact duplicates
        seen_attrs: set[tuple[str, str]] = set()
        merged_attrs: list[MentionAttribute] = []
        for item in group:
            for attr in item.attributes:
                attr_key = (attr.name.value, attr.value_text.strip())
                if attr_key not in seen_attrs:
                    seen_attrs.add(attr_key)
                    merged_attrs.append(attr)

        # Merge review flags
        merged_flags = list(dict.fromkeys(flag for item in group for flag in item.review_flags))

        # Create updated SourceRef
        updated_source = primary.source.model_copy(update={"occurrence_count": total_occurrences})

        merged_mention = primary.model_copy(
            update={
                "attributes": merged_attrs,
                "review_flags": merged_flags,
                "source": updated_source,
            }
        )
        deduped.append(merged_mention)

    return deduped


def deduplicate_relationships(relationships: Sequence[Relationship]) -> list[Relationship]:
    """Deduplicate extracted relationships across chunks."""
    grouped: dict[tuple[str, str, str, str, str], list[Relationship]] = {}

    for r in relationships:
        norm_quote = normalize_for_match(r.source.quote)
        key = (r.type.value, r.subject_mention_id, r.object_mention_id, r.source.unit_id, norm_quote)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    deduped: list[Relationship] = []
    for group in grouped.values():
        primary = group[0]
        if len(group) == 1:
            deduped.append(primary)
            continue

        total_occurrences = sum(item.source.occurrence_count for item in group)
        merged_flags = list(dict.fromkeys(flag for item in group for flag in item.review_flags))
        updated_source = primary.source.model_copy(update={"occurrence_count": total_occurrences})

        deduped.append(
            primary.model_copy(
                update={
                    "review_flags": merged_flags,
                    "source": updated_source,
                }
            )
        )

    return deduped


def deduplicate_events(events: Sequence[Event]) -> list[Event]:
    """Deduplicate extracted events across chunks."""
    grouped: dict[tuple[str, str, str, str], list[Event]] = {}

    for e in events:
        norm_quote = normalize_for_match(e.source.quote)
        key = (e.type.value, e.description.strip(), e.source.unit_id, norm_quote)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(e)

    deduped: list[Event] = []
    for group in grouped.values():
        primary = group[0]
        if len(group) == 1:
            deduped.append(primary)
            continue

        total_occurrences = sum(item.source.occurrence_count for item in group)
        merged_flags = list(dict.fromkeys(flag for item in group for flag in item.review_flags))
        updated_source = primary.source.model_copy(update={"occurrence_count": total_occurrences})

        deduped.append(
            primary.model_copy(
                update={
                    "review_flags": merged_flags,
                    "source": updated_source,
                }
            )
        )

    return deduped


def has_attribute_conflict(m1: Mention, m2: Mention) -> bool:
    """Check if two mentions have contradicting demographic attributes.

    Returns True if:
    - Differing father_name values (checked via name_key).
    - Differing dob values.
    - Differing age values with numeric difference > 2 years.
    """
    # 1. Father name check
    fn1 = [a.value_text.strip() for a in m1.attributes if a.name == AttrName.FATHER_NAME]
    fn2 = [a.value_text.strip() for a in m2.attributes if a.name == AttrName.FATHER_NAME]
    if fn1 and fn2:
        keys1 = {name_key(v) for v in fn1 if name_key(v)}
        keys2 = {name_key(v) for v in fn2 if name_key(v)}
        if keys1 and keys2 and keys1.isdisjoint(keys2):
            return True

    # 2. DOB check
    dob1 = {a.value_text.strip().lower() for a in m1.attributes if a.name == AttrName.DOB}
    dob2 = {a.value_text.strip().lower() for a in m2.attributes if a.name == AttrName.DOB}
    if dob1 and dob2 and dob1.isdisjoint(dob2):
        return True

    # 3. Age check
    ages1 = [extract_numeric_age(a.value_text) for a in m1.attributes if a.name == AttrName.AGE]
    ages2 = [extract_numeric_age(a.value_text) for a in m2.attributes if a.name == AttrName.AGE]
    valid_ages1 = [a for a in ages1 if a is not None]
    valid_ages2 = [a for a in ages2 if a is not None]

    if valid_ages1 and valid_ages2:
        for a1 in valid_ages1:
            for a2 in valid_ages2:
                if abs(a1 - a2) > 2:
                    return True

    return False


def cluster_persons_within_doc(
    mentions: Sequence[Mention],
    relationships: Sequence[Relationship],
    case_id: str,
    doc_id: str,
) -> tuple[list[LocalPersonCluster], list[ReviewItem]]:
    """Cluster PERSON mentions within a single document.

    Merges mentions into one local cluster only if:
    - Identical name_key OR linked by stated ALSO_KNOWN_AS relationship, AND
    - No contradicting attributes (dob, father_name, age).

    Two same-name people with contradicting attributes stay separate.
    """
    person_mentions = [m for m in mentions if m.type == EntityType.PERSON]
    if not person_mentions:
        return [], []

    # Map mention_id -> Mention
    {m.mention_id: m for m in person_mentions}

    # Find stated ALSO_KNOWN_AS alias links
    alias_graph: dict[str, set[str]] = {m.mention_id: set() for m in person_mentions}
    for r in relationships:
        if (
            r.type == RelType.ALSO_KNOWN_AS
            and r.subject_mention_id in alias_graph
            and r.object_mention_id in alias_graph
        ):
            alias_graph[r.subject_mention_id].add(r.object_mention_id)
            alias_graph[r.object_mention_id].add(r.subject_mention_id)

    # Disjoint-set union (DSU) or connected components
    parent = {m.mention_id: m.mention_id for m in person_mentions}

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    # Pairwise comparison
    n = len(person_mentions)
    for i in range(n):
        m1 = person_mentions[i]
        nk1 = name_key(m1.surface_text)
        for j in range(i + 1, n):
            m2 = person_mentions[j]
            nk2 = name_key(m2.surface_text)

            is_alias = m2.mention_id in alias_graph.get(m1.mention_id, set())
            same_name = bool(nk1 and nk2 and nk1 == nk2)

            if (is_alias or same_name) and not has_attribute_conflict(m1, m2):
                union(m1.mention_id, m2.mention_id)

    # Group mentions by root representative
    cluster_groups: dict[str, list[Mention]] = {}
    for m in person_mentions:
        root = find(m.mention_id)
        if root not in cluster_groups:
            cluster_groups[root] = []
        cluster_groups[root].append(m)

    clusters: list[LocalPersonCluster] = []
    review_items: list[ReviewItem] = []

    for group in cluster_groups.values():
        # Select canonical name: longest surface text
        canonical = max(group, key=lambda m: len(m.surface_text)).surface_text
        sorted_mids = sorted(m.mention_id for m in group)

        # Deterministic cluster ID
        clu_payload = f"{doc_id}|{'|'.join(sorted_mids)}".encode()
        cluster_id = f"CLU-{hashlib.sha1(clu_payload).hexdigest()[:12]}"

        all_name_keys = {name_key(m.surface_text) for m in group if name_key(m.surface_text)}

        # Union of attributes and sources (preserving all sources without dropping)
        all_attrs: list[MentionAttribute] = []
        all_sources: list[SourceRef] = []
        seen_attr_keys: set[tuple[str, str]] = set()

        for m in group:
            all_sources.append(m.source)
            for a in m.attributes:
                if a.source:
                    all_sources.append(a.source)
                a_key = (a.name.value, a.value_text.strip())
                if a_key not in seen_attr_keys:
                    seen_attr_keys.add(a_key)
                    all_attrs.append(a)

        cluster = LocalPersonCluster(
            cluster_id=cluster_id,
            case_id=case_id,
            doc_id=doc_id,
            canonical_name=canonical,
            name_keys=all_name_keys,
            mention_ids=sorted_mids,
            mentions=group,
            attributes=all_attrs,
            sources=all_sources,
        )
        clusters.append(cluster)

        # Check for contradictions inside the formed cluster
        clu_review_items = detect_contradictions(group, case_id=case_id, target_ids=sorted_mids)
        review_items.extend(clu_review_items)

    return clusters, review_items


def consolidate_within_doc(
    mentions: Sequence[Mention],
    relationships: Sequence[Relationship],
    events: Sequence[Event],
    case_id: str,
    doc_id: str,
) -> tuple[list[Mention], list[Relationship], list[Event], list[LocalPersonCluster], list[ReviewItem]]:
    """Run full within-document consolidation.

    1. Deduplicates mentions, relationships, and events across chunks.
    2. Clusters PERSON mentions within document and runs contradiction detection.
    """
    deduped_mentions = deduplicate_mentions(mentions)
    deduped_relationships = deduplicate_relationships(relationships)
    deduped_events = deduplicate_events(events)

    clusters, review_items = cluster_persons_within_doc(
        mentions=deduped_mentions,
        relationships=deduped_relationships,
        case_id=case_id,
        doc_id=doc_id,
    )

    return deduped_mentions, deduped_relationships, deduped_events, clusters, review_items


__all__ = [
    "LocalPersonCluster",
    "cluster_persons_within_doc",
    "consolidate_within_doc",
    "deduplicate_events",
    "deduplicate_mentions",
    "deduplicate_relationships",
    "has_attribute_conflict",
]
