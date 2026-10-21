"""Graph payload generation for ATLAS Dev 3.

Implements PLAN.md Section 4.6 and J4 specifications:
- Nodes: {node_id, label, props, case_ids[], evidence_ids[], canonical: bool}
  - Identifier nodes use global IDs: PHONE:{e164}, IMEI:{15 digits}, VEHICLE:{normalized}, ACCOUNT:{ifsc_or_bank|""}:{number}
  - Identifier nodes created ONLY when identifier_trust is in ('strong', 'confirmed').
  - Person nodes are per-case: PERSON:{case_id}:{cluster_id}
  - Case node: CASE:{case_id}
  - Other nodes: Organization, Location, Event
- Edges: {edge_id, type, src, dst, assertion, origin, evidence_ids[], case_ids[], canonical: bool, props}
  - Unapproved match suggestions produce edge CANDIDATE_MATCH with canonical: false
  - Approved matches produce edge SAME_AS with canonical: true referencing the audit action ID
- All nodes and edges carry case_ids and evidence_ids.
- Deterministic output (nodes sorted by node_id, edges sorted by edge_id).
"""

from __future__ import annotations

import re
from typing import Any

from atlas.contracts.enums import EntityType, IdentifierTrust
from atlas.contracts.ids import validate_case_id
from atlas.contracts.records import Event, Mention, Relationship, ResolutionSuggestion
from atlas.normalize.names import name_key

IDENTIFIER_ENTITY_TYPES = {
    EntityType.PHONE,
    EntityType.IMEI,
    EntityType.VEHICLE,
    EntityType.ACCOUNT,
}


def _clean_slug(text: str) -> str:
    """Produce a deterministic ASCII/alphanumeric identifier slug."""
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", text).strip("_")
    return slug or "unknown"


def _format_account_id(value: str) -> str:
    """Format account identifier node ID: ACCOUNT:{ifsc_or_bank|""}:{number}."""
    clean = value.strip()
    if clean.startswith("ACCOUNT:"):
        return clean
    if ":" in clean:
        return f"ACCOUNT:{clean}"
    return f"ACCOUNT::{clean}"


def build_graph_payload(
    case_id: str,
    mentions: list[Mention],
    relationships: list[Relationship],
    events: list[Event],
    suggestions: list[ResolutionSuggestion] | None = None,
    approved_merges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build canonical graph payload representation conforming to Section 4.6.

    Args:
        case_id: Validated case identifier.
        mentions: List of extracted entity mentions.
        relationships: List of extracted relationships between mentions.
        events: List of extracted event records.
        suggestions: Optional cross-case resolution suggestions.
        approved_merges: Optional approved merge audit links.

    Returns:
        Deterministic dict with 'nodes', 'edges', 'case_id', and 'state'.
    """
    validate_case_id(case_id)

    nodes_map: dict[str, dict[str, Any]] = {}
    mention_to_node: dict[str, str] = {}

    # 1. Create Case Node
    case_node_id = f"CASE:{case_id}"
    nodes_map[case_node_id] = {
        "node_id": case_node_id,
        "label": "Case",
        "props": {"case_id": case_id},
        "case_ids": [case_id],
        "evidence_ids": [],
        "canonical": True,
    }

    # 2. Process Mentions into Nodes
    for m in mentions:
        m_type = m.type
        trust_val = m.identifier_trust.value if hasattr(m.identifier_trust, "value") else str(m.identifier_trust)
        is_trusted = trust_val in (IdentifierTrust.STRONG.value, "confirmed") or (
            m.confirmed_by is not None and str(m.confirmed_by).strip() != ""
        )

        node_id: str | None = None
        label: str = "Unknown"
        props: dict[str, Any] = {}

        if m_type == EntityType.PHONE:
            if not is_trusted:
                continue
            val = (m.normalized_value or m.surface_text).strip()
            node_id = f"PHONE:{val}"
            label = "Phone"
            props = {"value": val, "surface_text": m.surface_text, "trust": trust_val}

        elif m_type == EntityType.IMEI:
            if not is_trusted:
                continue
            val = (m.normalized_value or m.surface_text).strip()
            node_id = f"IMEI:{val}"
            label = "Imei"
            props = {"value": val, "surface_text": m.surface_text, "trust": trust_val}

        elif m_type == EntityType.VEHICLE:
            if not is_trusted:
                continue
            val = (m.normalized_value or m.surface_text).strip()
            node_id = f"VEHICLE:{val}"
            label = "Vehicle"
            props = {"value": val, "surface_text": m.surface_text, "trust": trust_val}

        elif m_type == EntityType.ACCOUNT:
            if not is_trusted:
                continue
            val = (m.normalized_value or m.surface_text).strip()
            node_id = _format_account_id(val)
            label = "Account"
            props = {"value": val, "surface_text": m.surface_text, "trust": trust_val}

        elif m_type == EntityType.PERSON:
            label = "Person"
            if m.normalized_value and m.normalized_value.startswith("PERSON:"):
                node_id = m.normalized_value
            elif m.normalized_value:
                cluster_id = _clean_slug(m.normalized_value)
                node_id = f"PERSON:{case_id}:{cluster_id}"
            else:
                nk = name_key(m.surface_text)
                cluster_id = _clean_slug(nk) if nk else m.mention_id
                node_id = f"PERSON:{case_id}:{cluster_id}"

            props = {
                "name": m.surface_text,
                "role": m.stated_role.value if m.stated_role else "unknown",
            }
            for attr in m.attributes:
                attr_name = attr.name.value if hasattr(attr.name, "value") else str(attr.name)
                props[attr_name] = attr.value_text

        elif m_type == EntityType.ORGANIZATION:
            label = "Organization"
            slug = _clean_slug(m.normalized_value or m.surface_text)
            node_id = f"ORGANIZATION:{case_id}:{slug}"
            props = {"name": m.surface_text}

        elif m_type == EntityType.LOCATION:
            label = "Location"
            slug = _clean_slug(m.normalized_value or m.surface_text)
            node_id = f"LOCATION:{case_id}:{slug}"
            props = {"name": m.surface_text}

        if node_id:
            mention_to_node[m.mention_id] = node_id
            m_case_id = m.case_id or case_id

            if node_id in nodes_map:
                existing = nodes_map[node_id]
                if m_case_id not in existing["case_ids"]:
                    existing["case_ids"].append(m_case_id)
                if m.mention_id not in existing["evidence_ids"]:
                    existing["evidence_ids"].append(m.mention_id)
                # Merge props non-destructively
                for pk, pv in props.items():
                    if pk not in existing["props"] or not existing["props"][pk]:
                        existing["props"][pk] = pv
            else:
                nodes_map[node_id] = {
                    "node_id": node_id,
                    "label": label,
                    "props": props,
                    "case_ids": [m_case_id],
                    "evidence_ids": [m.mention_id],
                    "canonical": True,
                }

    # 3. Process Events into Nodes
    for ev in events:
        ev_node_id = ev.event_id if ev.event_id.startswith("EVENT:") else f"EVENT:{ev.event_id}"
        ev_case_id = ev.case_id or case_id
        ev_type = ev.type.value if hasattr(ev.type, "value") else str(ev.type)

        props = {
            "event_id": ev.event_id,
            "type": ev_type,
            "description": ev.description,
        }
        if ev.time:
            props["time"] = ev.time.original_text
            if ev.time.normalized_iso:
                props["time_iso"] = ev.time.normalized_iso

        nodes_map[ev_node_id] = {
            "node_id": ev_node_id,
            "label": "Event",
            "props": props,
            "case_ids": [ev_case_id],
            "evidence_ids": [ev.event_id],
            "canonical": True,
        }

    edges_map: dict[str, dict[str, Any]] = {}

    # 4. Process Relationships into Edges
    for r in relationships:
        src = mention_to_node.get(r.subject_mention_id, r.subject_mention_id)
        dst = mention_to_node.get(r.object_mention_id, r.object_mention_id)

        # Only create edge if both endpoints exist in the graph
        if src not in nodes_map or dst not in nodes_map:
            continue

        edge_type = r.type.value if hasattr(r.type, "value") else str(r.type)
        assertion_val = r.assertion.value if hasattr(r.assertion, "value") else str(r.assertion)
        origin_val = r.origin.value if hasattr(r.origin, "value") else str(r.origin)
        r_case_id = r.case_id or case_id

        edge_id = r.rel_id
        edges_map[edge_id] = {
            "edge_id": edge_id,
            "type": edge_type,
            "src": src,
            "dst": dst,
            "assertion": assertion_val,
            "origin": origin_val,
            "evidence_ids": sorted(list({r.rel_id, r.source.unit_id} if r.source else {r.rel_id})),
            "case_ids": [r_case_id],
            "canonical": True,
            "props": {},
        }

    # 5. Process Event Participants into Edges
    for ev in events:
        ev_node_id = ev.event_id if ev.event_id.startswith("EVENT:") else f"EVENT:{ev.event_id}"
        ev_case_id = ev.case_id or case_id
        ev_origin = ev.origin.value if hasattr(ev.origin, "value") else str(ev.origin)

        for p in ev.participants:
            part_node = mention_to_node.get(p.mention_id, p.mention_id)
            if part_node in nodes_map and ev_node_id in nodes_map:
                edge_id = f"EDGE-EV-{ev.event_id}-{p.mention_id}"
                edges_map[edge_id] = {
                    "edge_id": edge_id,
                    "type": "PARTICIPATED_IN",
                    "src": part_node,
                    "dst": ev_node_id,
                    "assertion": "stated",
                    "origin": ev_origin,
                    "evidence_ids": [ev.event_id],
                    "case_ids": [ev_case_id],
                    "canonical": True,
                    "props": {"role": p.role or "unknown"},
                }

        if ev.location_mention_id:
            loc_node = mention_to_node.get(ev.location_mention_id, ev.location_mention_id)
            if loc_node in nodes_map and ev_node_id in nodes_map:
                edge_id = f"EDGE-EV-LOC-{ev.event_id}-{ev.location_mention_id}"
                edges_map[edge_id] = {
                    "edge_id": edge_id,
                    "type": "LOCATED_AT",
                    "src": ev_node_id,
                    "dst": loc_node,
                    "assertion": "stated",
                    "origin": ev_origin,
                    "evidence_ids": [ev.event_id],
                    "case_ids": [ev_case_id],
                    "canonical": True,
                    "props": {},
                }

    # 6. Process Suggestions (CANDIDATE_MATCH, canonical: false)
    if suggestions:
        for sug in suggestions:
            src = mention_to_node.get(sug.mention_id, sug.mention_id)
            dst = sug.candidate_entity_id

            if src not in nodes_map:
                continue

            # Ensure candidate entity node exists in nodes
            if dst not in nodes_map:
                cand_case = sug.candidate_case_id or "EXTERNAL"
                nodes_map[dst] = {
                    "node_id": dst,
                    "label": "Person" if dst.startswith("PERSON:") else "Unknown",
                    "props": {"entity_id": dst},
                    "case_ids": [cand_case],
                    "evidence_ids": [],
                    "canonical": False,
                }

            status_val = sug.status.value if hasattr(sug.status, "value") else str(sug.status)
            cand_cases: list[str] = [c for c in (sug.case_id, sug.candidate_case_id) if c is not None]
            case_ids = sorted(list(set(cand_cases)))
            if not case_ids:
                case_ids = [case_id]

            edge_id = f"EDGE-SUG-{sug.suggestion_id}"
            edges_map[edge_id] = {
                "edge_id": edge_id,
                "type": "CANDIDATE_MATCH",
                "src": src,
                "dst": dst,
                "assertion": "model_inferred",
                "origin": "model_inferred",
                "evidence_ids": sorted(list({sug.suggestion_id, sug.mention_id})),
                "case_ids": case_ids,
                "canonical": False,
                "props": {
                    "heuristic_rank": sug.heuristic_rank,
                    "rank_note": sug.rank_note,
                    "status": status_val,
                    "explanation": sug.explanation,
                },
            }

    # 7. Process Approved Merges (SAME_AS, canonical: true)
    if approved_merges:
        for merge in approved_merges:
            if isinstance(merge, dict):
                # Filter out split links
                if merge.get("status") == "split":
                    continue

                src_val = merge.get("entity_id_1")
                dst_val = merge.get("entity_id_2")
                action_id = str(merge.get("action_id", "APPROVED"))
                m_case = str(merge.get("case_id", case_id))

                if not src_val or not dst_val:
                    target_ids = merge.get("target_ids", [])
                    if isinstance(target_ids, (list, tuple)) and len(target_ids) >= 2:
                        src_val = target_ids[0]
                        dst_val = target_ids[1]

                if not src_val or not dst_val:
                    continue

                src = str(src_val)
                dst = str(dst_val)

                # Ensure endpoints exist
                for entity_id in (src, dst):
                    if entity_id not in nodes_map:
                        nodes_map[entity_id] = {
                            "node_id": entity_id,
                            "label": "Person" if entity_id.startswith("PERSON:") else "Unknown",
                            "props": {"entity_id": entity_id},
                            "case_ids": [m_case],
                            "evidence_ids": [action_id],
                            "canonical": True,
                        }

                edge_id = f"EDGE-MERGE-{action_id}-{src}-{dst}"
                edges_map[edge_id] = {
                    "edge_id": edge_id,
                    "type": "SAME_AS",
                    "src": src,
                    "dst": dst,
                    "assertion": "stated",
                    "origin": "model_inferred",
                    "evidence_ids": [action_id],
                    "case_ids": sorted(list({case_id, m_case})),
                    "canonical": True,
                    "props": {
                        "action_id": action_id,
                        "audit_action_id": action_id,
                    },
                }

    # 8. Sort nodes and edges deterministically
    sorted_nodes = sorted(nodes_map.values(), key=lambda n: n["node_id"])
    sorted_edges = sorted(edges_map.values(), key=lambda e: e["edge_id"])

    # Ensure inner case_ids and evidence_ids lists are sorted
    for n in sorted_nodes:
        n["case_ids"] = sorted(list(set(n.get("case_ids", []))))
        n["evidence_ids"] = sorted(list(set(n.get("evidence_ids", []))))

    for e in sorted_edges:
        e["case_ids"] = sorted(list(set(e.get("case_ids", []))))
        e["evidence_ids"] = sorted(list(set(e.get("evidence_ids", []))))

    return {
        "case_id": case_id,
        "state": "completed",
        "nodes": sorted_nodes,
        "edges": sorted_edges,
    }


__all__ = ["build_graph_payload"]
