from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EntityStorePort(Protocol):
    """Port interface for entity storage, candidate queries, and audit logging."""

    def query_candidates(
        self,
        auth: Any,
        identifier_keys: list[str],
        name_keys: list[str],
    ) -> list[dict[str, Any]]:
        """Query cross-case candidate entities matching identifiers or names, filtered by authorization."""
        ...

    def store_mentions(self, case_id: str, mentions: list[Any]) -> None:
        """Persist extracted mentions for a case."""
        ...

    def store_suggestions(self, case_id: str, suggestions: list[Any]) -> None:
        """Persist resolution suggestions for a case."""
        ...

    def record_action(self, action: Any) -> None:
        """Record an audited review action to the append-only log."""
        ...

    def verify_chain(self) -> bool:
        """Verify cryptographic integrity of the hash-chained audit log."""
        ...


__all__ = ["EntityStorePort"]
