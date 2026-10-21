"""Adapter mapping layer for Dev 4 Graph Database / Visualization integration.

Implements PLAN.md Section 4.6 and J4 specifications:
- format_for_dev4(graph_payload: dict, format_name: str = 'generic') -> dict
- Configurable per config/defaults.yaml setting 'dev4_graph_format'.
- Supports 'generic', 'cytoscape', 'd3', and 'dev4' export schemas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _load_default_dev4_format() -> str:
    """Load default graph format setting from config/defaults.yaml."""
    defaults_path = Path("config/defaults.yaml")
    if defaults_path.is_file():
        try:
            content = defaults_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "dev4_graph_format" in data:
                return str(data["dev4_graph_format"]).strip().lower()
        except Exception:
            pass
    return "generic"


def format_for_dev4(
    graph_payload: dict[str, Any],
    format_name: str | None = None,
) -> dict[str, Any]:
    """Transform canonical graph payload into target Dev 4 format.

    Args:
        graph_payload: Canonical graph payload with 'nodes' and 'edges'.
        format_name: Target format identifier ('generic', 'cytoscape', 'd3', 'dev4').
            Defaults to setting in config/defaults.yaml if omitted.

    Returns:
        Formatted graph dictionary according to target schema.

    Raises:
        ValueError: If format_name is unrecognized.
    """
    selected_format = (format_name or _load_default_dev4_format()).strip().lower()

    nodes = list(graph_payload.get("nodes", []))
    edges = list(graph_payload.get("edges", []))
    case_id = graph_payload.get("case_id", "")
    state = graph_payload.get("state", "completed")

    if selected_format in ("generic", "raw", "default"):
        return {
            "case_id": case_id,
            "state": state,
            "format": "generic",
            "nodes": nodes,
            "edges": edges,
        }

    elif selected_format in ("cytoscape", "cytoscape_json"):
        cy_nodes = []
        for n in nodes:
            data = {
                "id": n["node_id"],
                "label": n.get("label", "Entity"),
                "canonical": n.get("canonical", True),
                "case_ids": n.get("case_ids", []),
                "evidence_ids": n.get("evidence_ids", []),
            }
            props = n.get("props", {})
            if isinstance(props, dict):
                data.update(props)
            cy_nodes.append({"data": data})

        cy_edges = []
        for e in edges:
            data = {
                "id": e["edge_id"],
                "source": e["src"],
                "target": e["dst"],
                "type": e.get("type", "RELATED_TO"),
                "canonical": e.get("canonical", True),
                "assertion": e.get("assertion", "stated"),
                "origin": e.get("origin", "unknown"),
                "case_ids": e.get("case_ids", []),
                "evidence_ids": e.get("evidence_ids", []),
            }
            props = e.get("props", {})
            if isinstance(props, dict):
                data.update(props)
            cy_edges.append({"data": data})

        return {
            "case_id": case_id,
            "state": state,
            "format": "cytoscape",
            "elements": {
                "nodes": cy_nodes,
                "edges": cy_edges,
            },
        }

    elif selected_format in ("d3", "node_link", "d3_json"):
        d3_nodes = []
        for n in nodes:
            entry = dict(n)
            entry["id"] = n["node_id"]
            d3_nodes.append(entry)

        d3_links = []
        for e in edges:
            entry = dict(e)
            entry["source"] = e["src"]
            entry["target"] = e["dst"]
            entry["id"] = e["edge_id"]
            d3_links.append(entry)

        return {
            "case_id": case_id,
            "state": state,
            "format": "d3",
            "nodes": d3_nodes,
            "links": d3_links,
        }

    elif selected_format == "dev4":
        return {
            "case_id": case_id,
            "state": state,
            "format": "dev4",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    else:
        raise ValueError(
            f"Unsupported Dev4 graph format '{selected_format}'. Supported formats: generic, cytoscape, d3, dev4."
        )


__all__ = ["format_for_dev4"]
