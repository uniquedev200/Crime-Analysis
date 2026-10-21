from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LlmClientPort(Protocol):
    """Port interface for schema-constrained LLM narrative extraction."""

    @property
    def provider_name(self) -> str:
        """Name of the LLM provider (e.g. 'mock', 'openai', 'gemini')."""
        ...

    @property
    def model_name(self) -> str:
        """Name of the active model."""
        ...

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Perform schema-constrained extraction returning model output dictionary."""
        ...


__all__ = ["LlmClientPort"]
