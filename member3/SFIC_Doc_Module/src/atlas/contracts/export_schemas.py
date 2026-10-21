"""Export JSON Schemas for all ATLAS contract models to output directory."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel

from atlas.contracts.model_schema import MODEL_SCHEMA, ModelOutput
from atlas.contracts.records import (
    Aggregate,
    CaseResult,
    DocumentRecord,
    Event,
    Mention,
    OcrInfo,
    Rejection,
    Relationship,
    ResolutionSuggestion,
    ReviewAction,
    ReviewItem,
    RunMeta,
    SourceRef,
)


def _to_snake_case(name: str) -> str:
    """Convert PascalCase name to snake_case."""
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def export_schemas(out_dir: Path | str) -> dict[str, Path]:
    """Export JSON Schema definitions for all contract models into the specified directory.

    Writes UTF-8 formatted, indented JSON files with ensure_ascii=False.
    Returns mapping from schema name to output Path.
    """
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    models: list[type[BaseModel]] = [
        SourceRef,
        OcrInfo,
        Mention,
        Relationship,
        Event,
        Aggregate,
        ReviewItem,
        Rejection,
        DocumentRecord,
        RunMeta,
        CaseResult,
        ResolutionSuggestion,
        ReviewAction,
        ModelOutput,
    ]

    exported: dict[str, Path] = {}

    for model_cls in models:
        schema = model_cls.model_json_schema()
        snake_name = _to_snake_case(model_cls.__name__)
        out_file = target_dir / f"{snake_name}.schema.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        exported[snake_name] = out_file

    # Also export the hand-written provider LLM schema
    provider_file = target_dir / "provider_model.schema.json"
    with open(provider_file, "w", encoding="utf-8") as f:
        json.dump(MODEL_SCHEMA, f, indent=2, ensure_ascii=False)
    exported["provider_model"] = provider_file

    return exported


__all__ = ["export_schemas"]
