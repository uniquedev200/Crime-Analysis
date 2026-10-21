"""Within-case cross-document consolidation and entity linking.

Implements PLAN.md Section 5.6 and H3 specifications:
1. Unifies identifier mentions with trust in ('strong', 'confirmed') across documents
   by normalized value (e.g., phone in FIR connects to same phone in CDR / bank).
2. OCR-derived identifiers without confirmation remain 'review_required' and DO NOT
   unify across documents or create unified nodes.
3. Person clusters merge across documents only when:
   - name_key matches AND
   - (shared strong/confirmed identifier link OR matching father_name / dob attribute) AND
   - no contradictions between attributes.
   Otherwise they stay separate and a within-case 'match_candidate' review item is created.
4. Detects attribute contradictions (differing father_name, dob, or age beyond +-2 years)
   and creates 'contradiction' review items holding all values and sources.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from atlas.consolidate.contradictions import detect_contradictions
from atlas.consolidate.within_doc import has_attribute_conflict
from atlas.contracts.enums import (
    AttrName,
    EntityType,
    IdentifierTrust,
    ReviewItemStatus,
    ReviewKind,
)
from atlas.contracts.ids import make_review_id, validate_case_id
from atlas.contracts.records import (
    Aggregate,
    DocumentRecord,
    Event,
    EventParticipant,
    Mention,
    MentionAttribute,
    Relationship,
    ReviewItem,
)
from atlas.normalize.names import name_key

IDENTIFIER_ENTITY_TYPES = {
    EntityType.PHONE,
    EntityType.IMEI,
    EntityType.VEHICLE,
    EntityType.ACCOUNT,
}


def _are_attributes_matching(val1: str, val2: str) -> bool:
    """Check if two attribute values match after casefolding and whitespace normalization."""
    v1 = " ".join(val1.casefold().strip().split())
    v2 = " ".join(val2.casefold().strip().split())
    if not v1 or not v2:
        return False
    if v1 == v2:
        return True
    # If both could be names, compare name_keys
    nk1 = name_key(val1)
    nk2 = name_key(val2)
    return bool(nk1 and nk2 and nk1 == nk2)


def consolidate_within_case(
    doc_results: Sequence[DocumentRecord | Any] | None = None,
    case_id: str = "",
    *,
    mentions: Sequence[Mention] | None = None,
    relationships: Sequence[Relationship] | None = None,
    events: Sequence[Event] | None = None,
    aggregates: Sequence[Aggregate] | None = None,
    review_items: Sequence[ReviewItem] | None = None,
    **kwargs: Any,
) -> tuple[list[Mention], list[Relationship], list[Event], list[Aggregate], list[ReviewItem]]:
    """Run within-case cross-document consolidation.

    Unifies strong/confirmed identifiers, merges corroborating person clusters,
    preserves unconfirmed OCR identifiers in review_required state, and generates
    match_candidate and contradiction review items.
    """
    raw_mentions: list[Mention] = list(mentions or [])
    raw_relationships: list[Relationship] = list(relationships or [])
    raw_events: list[Event] = list(events or [])
    raw_aggregates: list[Aggregate] = list(aggregates or [])
    raw_review_items: list[ReviewItem] = list(review_items or [])

    # Extract facts from doc_results if provided
    if doc_results:
        for item in doc_results:
            if hasattr(item, "mentions") and isinstance(item.mentions, list):
                raw_mentions.extend(item.mentions)
            if hasattr(item, "relationships") and isinstance(item.relationships, list):
                raw_relationships.extend(item.relationships)
            if hasattr(item, "events") and isinstance(item.events, list):
                raw_events.extend(item.events)
            if hasattr(item, "aggregates") and isinstance(item.aggregates, list):
                raw_aggregates.extend(item.aggregates)
            if hasattr(item, "review_items") and isinstance(item.review_items, list):
                raw_review_items.extend(item.review_items)
            elif isinstance(item, Mention):
                raw_mentions.append(item)
            elif isinstance(item, Relationship):
                raw_relationships.append(item)
            elif isinstance(item, Event):
                raw_events.append(item)
            elif isinstance(item, Aggregate):
                raw_aggregates.append(item)
            elif isinstance(item, ReviewItem):
                raw_review_items.append(item)

    if not case_id and raw_mentions:
        case_id = raw_mentions[0].case_id

    if case_id:
        validate_case_id(case_id)

    # 1. Unify identifier mentions across documents
    # Strong or confirmed identifiers unify by normalized value.
    # Unconfirmed OCR identifiers (review_required) do NOT unify.
    mention_remap: dict[str, str] = {}
    id_groups: dict[tuple[str, str], list[Mention]] = {}

    for m in raw_mentions:
        is_identifier = m.type in IDENTIFIER_ENTITY_TYPES
        is_trusted = (m.identifier_trust == IdentifierTrust.STRONG) or (m.confirmed_by is not None)

        if is_identifier and is_trusted and m.normalized_value:
            group_key = (m.type.value, m.normalized_value)
            if group_key not in id_groups:
                id_groups[group_key] = []
            id_groups[group_key].append(m)

    unified_identifiers: dict[str, Mention] = {}
    for group in id_groups.values():
        if len(group) == 1:
            continue
        # Sort group deterministically
        sorted_group = sorted(group, key=lambda m: (m.doc_id, m.mention_id))
        primary = sorted_group[0]
        canonical_mid = primary.mention_id

        # Merge occurrence count, attributes, and review flags
        total_occurrences = sum(item.source.occurrence_count for item in sorted_group)
        seen_attrs: set[tuple[str, str]] = set()
        merged_attrs: list[MentionAttribute] = []
        for item in sorted_group:
            for attr in item.attributes:
                a_key = (attr.name.value, attr.value_text.strip())
                if a_key not in seen_attrs:
                    seen_attrs.add(a_key)
                    merged_attrs.append(attr)

        merged_flags = list(dict.fromkeys(flag for item in sorted_group for flag in item.review_flags))
        updated_source = primary.source.model_copy(update={"occurrence_count": total_occurrences})

        unified_mention = primary.model_copy(
            update={
                "attributes": merged_attrs,
                "review_flags": merged_flags,
                "source": updated_source,
            }
        )
        unified_identifiers[canonical_mid] = unified_mention

        for item in sorted_group:
            mention_remap[item.mention_id] = canonical_mid

    # 2. Extract person mentions and their linked strong/confirmed identifiers
    # Map person mention_id -> set of canonical identifier mention_ids
    person_identifier_links: dict[str, set[str]] = {}
    for r in raw_relationships:
        sub_id = mention_remap.get(r.subject_mention_id, r.subject_mention_id)
        obj_id = mention_remap.get(r.object_mention_id, r.object_mention_id)
        # Check if subject is person and object is unified identifier or strong/confirmed identifier
        if sub_id not in person_identifier_links:
            person_identifier_links[sub_id] = set()
        if obj_id not in person_identifier_links:
            person_identifier_links[obj_id] = set()

        person_identifier_links[sub_id].add(obj_id)
        person_identifier_links[obj_id].add(sub_id)

    # 3. Person cross-document consolidation
    person_mentions = [m for m in raw_mentions if m.type == EntityType.PERSON]

    # Disjoint-set union for person mentions
    parent = {m.mention_id: m.mention_id for m in person_mentions}

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    new_review_items: list[ReviewItem] = []
    seen_candidate_pairs: set[tuple[str, str]] = set()

    n = len(person_mentions)
    for i in range(n):
        m1 = person_mentions[i]
        nk1 = name_key(m1.surface_text)
        if not nk1:
            continue

        for j in range(i + 1, n):
            m2 = person_mentions[j]
            nk2 = name_key(m2.surface_text)
            if not nk2 or nk1 != nk2:
                continue

            # Same name_key!
            # Check for attribute contradictions (differing father, dob, or age)
            has_conflict = has_attribute_conflict(m1, m2)
            if has_conflict:
                # Add contradiction review items
                pair_target_ids = sorted([m1.mention_id, m2.mention_id])
                pair_contradictions = detect_contradictions([m1, m2], case_id=case_id, target_ids=pair_target_ids)
                new_review_items.extend(pair_contradictions)
                continue

            # Check if there is corroborating evidence:
            # (a) Shared strong/confirmed identifier link
            ids1 = person_identifier_links.get(m1.mention_id, set()) | person_identifier_links.get(
                mention_remap.get(m1.mention_id, m1.mention_id), set()
            )
            ids2 = person_identifier_links.get(m2.mention_id, set()) | person_identifier_links.get(
                mention_remap.get(m2.mention_id, m2.mention_id), set()
            )
            shared_ids = ids1 & ids2

            # (b) Matching father_name or dob attribute
            matching_father = False
            matching_dob = False

            f1 = [a.value_text for a in m1.attributes if a.name == AttrName.FATHER_NAME]
            f2 = [a.value_text for a in m2.attributes if a.name == AttrName.FATHER_NAME]
            for val1 in f1:
                for val2 in f2:
                    if _are_attributes_matching(val1, val2):
                        matching_father = True
                        break

            d1 = [a.value_text for a in m1.attributes if a.name == AttrName.DOB]
            d2 = [a.value_text for a in m2.attributes if a.name == AttrName.DOB]
            for val1 in d1:
                for val2 in d2:
                    if _are_attributes_matching(val1, val2):
                        matching_dob = True
                        break

            can_merge = bool(shared_ids or matching_father or matching_dob)

            if can_merge:
                union(m1.mention_id, m2.mention_id)
            else:
                # Same name_key across documents without corroboration -> match_candidate review item
                # Only if different documents or distinct clusters
                pair_key = (min(m1.mention_id, m2.mention_id), max(m1.mention_id, m2.mention_id))
                if pair_key not in seen_candidate_pairs and m1.doc_id != m2.doc_id:
                    seen_candidate_pairs.add(pair_key)
                    rev_id = make_review_id(
                        case_id=case_id,
                        kind=ReviewKind.MATCH_CANDIDATE.value,
                        target_id=f"{pair_key[0]}|{pair_key[1]}",
                        detail=f"Person match candidate with matching name_key '{nk1}' across documents",
                    )
                    candidate_item = ReviewItem(
                        review_id=rev_id,
                        case_id=case_id,
                        kind=ReviewKind.MATCH_CANDIDATE,
                        target_ids=[pair_key[0], pair_key[1]],
                        detail=(
                            f"Person match candidate with matching name_key '{nk1}' between "
                            f"{m1.doc_id} and {m2.doc_id} requiring corroboration."
                        ),
                        status=ReviewItemStatus.OPEN,
                    )
                    new_review_items.append(candidate_item)

    # 4. Finalize person mention merging
    person_clusters: dict[str, list[Mention]] = {}
    for m in person_mentions:
        root = find(m.mention_id)
        if root not in person_clusters:
            person_clusters[root] = []
        person_clusters[root].append(m)

    unified_persons: dict[str, Mention] = {}
    for group in person_clusters.values():
        if len(group) == 1:
            continue
        sorted_group = sorted(group, key=lambda m: (m.doc_id, m.mention_id))
        primary = sorted_group[0]
        canonical_mid = primary.mention_id

        # Merge attributes and review flags
        seen_attrs = set()
        merged_attrs = []
        for item in sorted_group:
            for attr in item.attributes:
                a_key = (attr.name.value, attr.value_text.strip())
                if a_key not in seen_attrs:
                    seen_attrs.add(a_key)
                    merged_attrs.append(attr)

        merged_flags = list(dict.fromkeys(flag for item in sorted_group for flag in item.review_flags))
        total_occurrences = sum(item.source.occurrence_count for item in sorted_group)
        updated_source = primary.source.model_copy(update={"occurrence_count": total_occurrences})

        # Canonical surface text: longest
        canonical_name = max(sorted_group, key=lambda m: len(m.surface_text)).surface_text

        unified_person = primary.model_copy(
            update={
                "surface_text": canonical_name,
                "attributes": merged_attrs,
                "review_flags": merged_flags,
                "source": updated_source,
            }
        )
        unified_persons[canonical_mid] = unified_person

        for item in sorted_group:
            mention_remap[item.mention_id] = canonical_mid

    # 5. Build final list of mentions
    final_mentions: list[Mention] = []
    seen_mids: set[str] = set()

    for m in raw_mentions:
        canonical_mid = mention_remap.get(m.mention_id, m.mention_id)
        if canonical_mid in seen_mids:
            continue
        seen_mids.add(canonical_mid)

        if canonical_mid in unified_identifiers:
            final_mentions.append(unified_identifiers[canonical_mid])
        elif canonical_mid in unified_persons:
            final_mentions.append(unified_persons[canonical_mid])
        else:
            final_mentions.append(m)

    # 6. Update relationships with remapped mention IDs and deduplicate
    final_relationships: list[Relationship] = []
    seen_rels: set[tuple[str, str, str]] = set()

    for r in raw_relationships:
        sub_id = mention_remap.get(r.subject_mention_id, r.subject_mention_id)
        obj_id = mention_remap.get(r.object_mention_id, r.object_mention_id)

        # Avoid self-referential relationships produced by merging
        if sub_id == obj_id:
            continue

        rel_key = (r.type.value, sub_id, obj_id)
        if rel_key in seen_rels:
            continue
        seen_rels.add(rel_key)

        updated_r = r.model_copy(
            update={
                "subject_mention_id": sub_id,
                "object_mention_id": obj_id,
            }
        )
        final_relationships.append(updated_r)

    # 7. Update events with remapped participant IDs
    final_events: list[Event] = []
    for e in raw_events:
        updated_participants: list[EventParticipant] = []
        for p in e.participants:
            remap_pid = mention_remap.get(p.mention_id, p.mention_id)
            updated_participants.append(p.model_copy(update={"mention_id": remap_pid}))

        loc_id = e.location_mention_id
        if loc_id and loc_id in mention_remap:
            loc_id = mention_remap[loc_id]

        updated_e = e.model_copy(
            update={
                "participants": updated_participants,
                "location_mention_id": loc_id,
            }
        )
        final_events.append(updated_e)

    # 8. Update aggregates with remapped subject/object IDs
    final_aggregates: list[Aggregate] = []
    for agg in raw_aggregates:
        sub_id = mention_remap.get(agg.subject_mention_id, agg.subject_mention_id)
        obj_id = mention_remap.get(agg.object_mention_id, agg.object_mention_id)
        updated_agg = agg.model_copy(
            update={
                "subject_mention_id": sub_id,
                "object_mention_id": obj_id,
            }
        )
        final_aggregates.append(updated_agg)

    # 9. Combine review items
    final_review_items = list(raw_review_items)
    # Deduplicate review items by review_id
    seen_rev_ids = {item.review_id for item in final_review_items}
    for item in new_review_items:
        if item.review_id not in seen_rev_ids:
            seen_rev_ids.add(item.review_id)
            final_review_items.append(item)

    return (
        final_mentions,
        final_relationships,
        final_events,
        final_aggregates,
        final_review_items,
    )


__all__ = ["consolidate_within_case"]
