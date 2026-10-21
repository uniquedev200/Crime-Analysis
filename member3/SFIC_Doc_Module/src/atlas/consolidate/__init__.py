"""Consolidation package for ATLAS Dev 3."""

from __future__ import annotations

from atlas.consolidate.contradictions import detect_contradictions, extract_numeric_age
from atlas.consolidate.within_doc import (
    LocalPersonCluster,
    cluster_persons_within_doc,
    consolidate_within_doc,
    deduplicate_events,
    deduplicate_mentions,
    deduplicate_relationships,
    has_attribute_conflict,
)

__all__ = [
    "LocalPersonCluster",
    "cluster_persons_within_doc",
    "consolidate_within_doc",
    "deduplicate_events",
    "deduplicate_mentions",
    "deduplicate_relationships",
    "detect_contradictions",
    "extract_numeric_age",
    "has_attribute_conflict",
]
