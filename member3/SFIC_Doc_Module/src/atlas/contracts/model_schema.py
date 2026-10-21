"""Provider-safe JSON schema and output validation for LLM extraction responses.

Enforces provider-compatible structured output rules (OpenAI / Gemini):
- Every property is in required
- Optionals are explicit ["type", "null"] unions
- additionalProperties: false everywhere
- String enums for categorical fields
- No oneOf, defaults, minLength, pattern, or format
- Maximum nesting depth of 4
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from atlas.contracts.enums import AttrName, EntityType, EventType, RelType, StatedRole

MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "local_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "PERSON",
                            "PHONE",
                            "IMEI",
                            "VEHICLE",
                            "ACCOUNT",
                            "ORGANIZATION",
                            "LOCATION",
                        ],
                    },
                    "surface_text": {"type": "string"},
                    "role_stated": {
                        "type": ["string", "null"],
                        "enum": [
                            "complainant",
                            "accused",
                            "suspect",
                            "witness",
                            "victim",
                            "officer",
                            "other",
                            "unknown",
                            None,
                        ],
                    },
                    "unit_id": {"type": "string"},
                    "quote": {"type": "string"},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "enum": [
                                        "father_name",
                                        "age",
                                        "dob",
                                        "gender",
                                        "address",
                                        "occupation",
                                    ],
                                },
                                "value_text": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["name", "value_text", "quote"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "local_id",
                    "type",
                    "surface_text",
                    "role_stated",
                    "unit_id",
                    "quote",
                    "attributes",
                ],
                "additionalProperties": False,
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "USES_PHONE",
                            "USES_DEVICE",
                            "OWNS_VEHICLE",
                            "HOLDS_ACCOUNT",
                            "ASSOCIATED_WITH",
                            "EMPLOYED_BY",
                            "LOCATED_AT",
                            "ALSO_KNOWN_AS",
                            "CALLED",
                            "TRANSFERRED_TO",
                        ],
                    },
                    "subject_local_id": {"type": "string"},
                    "object_local_id": {"type": "string"},
                    "unit_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "type",
                    "subject_local_id",
                    "object_local_id",
                    "unit_id",
                    "quote",
                ],
                "additionalProperties": False,
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "INCIDENT",
                            "CALL",
                            "TRANSACTION",
                            "MEETING",
                            "ARREST",
                            "SIGHTING",
                            "OTHER",
                        ],
                    },
                    "description": {"type": "string"},
                    "time_text": {"type": ["string", "null"]},
                    "participant_local_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "location_local_id": {"type": ["string", "null"]},
                    "unit_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "type",
                    "description",
                    "time_text",
                    "participant_local_ids",
                    "location_local_id",
                    "unit_id",
                    "quote",
                ],
                "additionalProperties": False,
            },
        },
        "notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["mentions", "relationships", "events", "notes"],
    "additionalProperties": False,
}


class ModelAttributeOutput(BaseModel):
    """Attribute entry inside a model mention."""

    model_config = ConfigDict(extra="forbid")

    name: AttrName
    value_text: str
    quote: str


class ModelMentionOutput(BaseModel):
    """Mention extracted by LLM."""

    model_config = ConfigDict(extra="forbid")

    local_id: str
    type: EntityType
    surface_text: str
    role_stated: StatedRole | None = None
    unit_id: str
    quote: str
    attributes: list[ModelAttributeOutput]


class ModelRelationshipOutput(BaseModel):
    """Relationship extracted by LLM."""

    model_config = ConfigDict(extra="forbid")

    type: RelType
    subject_local_id: str
    object_local_id: str
    unit_id: str
    quote: str


class ModelEventOutput(BaseModel):
    """Event extracted by LLM."""

    model_config = ConfigDict(extra="forbid")

    type: EventType
    description: str
    time_text: str | None = None
    participant_local_ids: list[str]
    location_local_id: str | None = None
    unit_id: str
    quote: str


class ModelOutput(BaseModel):
    """Root structure of LLM response."""

    model_config = ConfigDict(extra="forbid")

    mentions: list[ModelMentionOutput]
    relationships: list[ModelRelationshipOutput]
    events: list[ModelEventOutput]
    notes: list[str]


def lint_provider_schema(schema: dict[str, Any], max_depth: int = 4) -> list[str]:
    """Strictly audit a JSON Schema dictionary against provider rules.

    Rules checked:
    - Every object property is required
    - additionalProperties: false on every object
    - Optionals are explicit ["type", "null"] unions (no anyOf/oneOf/allOf)
    - Enums contain only string (or null/None) values
    - No forbidden keys: oneOf, allOf, anyOf, default, minLength, pattern, format
    - Nesting depth does not exceed max_depth
    """
    errors: list[str] = []

    def _walk(node: Any, path: str, depth: int) -> None:
        if depth > max_depth:
            errors.append(f"{path}: depth {depth} exceeds maximum allowable depth {max_depth}")

        if not isinstance(node, dict):
            return

        # Check forbidden keywords
        for forbidden in ("oneOf", "allOf", "anyOf", "default", "minLength", "pattern", "format"):
            if forbidden in node:
                errors.append(f"{path}: forbidden keyword '{forbidden}' present")

        # Object assertions
        node_type = node.get("type")
        if node_type == "object":
            if node.get("additionalProperties") is not False:
                errors.append(f"{path}: additionalProperties must be explicitly False")

            props = node.get("properties", {})
            required_list = node.get("required", [])

            missing_req = set(props.keys()) - set(required_list)
            if missing_req:
                errors.append(f"{path}: properties {sorted(missing_req)} not listed in required")

            for prop_name, prop_val in props.items():
                _walk(prop_val, f"{path}.{prop_name}", depth + 1)

        # Array assertions
        elif node_type == "array":
            items = node.get("items")
            if items:
                _walk(items, f"{path}[]", depth)

        # Enum assertions
        if "enum" in node:
            for val in node["enum"]:
                if val is not None and not isinstance(val, str):
                    errors.append(f"{path}: enum value {val!r} is not a string or null")

    _walk(schema, "root", 1)
    return errors


def validate_model_output(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate raw LLM JSON response against provider-safe model schema.

    Enforces strict typing, required fields, and rejects any unexpected fields.
    Raises ValueError on failure. Returns validated dictionary on success.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"Model output must be a dict, got {type(raw).__name__}")
    try:
        validated = ModelOutput.model_validate(raw)
        return validated.model_dump(mode="python")
    except Exception as exc:
        raise ValueError(f"Model output failed schema validation: {exc}") from exc


__all__ = [
    "MODEL_SCHEMA",
    "ModelAttributeOutput",
    "ModelEventOutput",
    "ModelMentionOutput",
    "ModelOutput",
    "ModelRelationshipOutput",
    "lint_provider_schema",
    "validate_model_output",
]
