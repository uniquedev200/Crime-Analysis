from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphSinkPort(Protocol):
    """Port interface for pushing graph nodes and edges to graph storage."""

    def push_nodes(self, nodes: list[dict[str, Any]]) -> None:
        """Push node payloads to the graph sink."""
        ...

    def push_edges(self, edges: list[dict[str, Any]]) -> None:
        """Push edge payloads to the graph sink."""
        ...


__all__ = ["GraphSinkPort"]
