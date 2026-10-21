"""Pydantic v2 record schemas for ATLAS Dev 3 contracts.

All models configure extra="forbid", UTF-8 string encoding, and strict case_id validation
to prevent directory traversal and injection attacks at Gate 0.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from atlas.contracts.enums import (
    Assertion,
    AttrName,
    DocumentStatus,
    EntityType,
    EventType,
    IdentifierTrust,
    JobState,
    NormalizationStatus,
    OcrLevel,
    Origin,
    PageMethod,
    QuoteStatus,
    RejectionKind,
    RelType,
    ReviewActionType,
    ReviewItemStatus,
    ReviewKind,
    SheetState,
    SignalPolarity,
    StatedRole,
    SuggestionStatus,
    TimeAmbiguity,
    UnitKind,
)
from atlas.contracts.ids import validate_case_id


class OcrInfo(BaseModel):
    """OCR confidence scoring and engine metadata."""

    model_config = ConfigDict(extra="forbid")

    level: OcrLevel
    min: float | None = None
    mean: float | None = None
    score_kind: str = "engine_score_not_probability"
    engine: str
    langs: list[str] = Field(default_factory=list)


class SourceRef(BaseModel):
    """Exact source location reference in an ingested document."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    file_name: str
    file_sha256: str
    unit_id: str
    unit_kind: UnitKind
    page: int | None = None
    sheet: str | None = None
    row: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    bbox: list[float] | None = None
    text_origin: Origin
    quote: str
    quote_status: QuoteStatus
    occurrence_count: int = 1


class ValidationCheck(BaseModel):
    """Result of an individual deterministic validator check."""

    model_config = ConfigDict(extra="forbid")

    name: str
    passed: bool
    detail: str | None = None


class MentionAttribute(BaseModel):
    """Demographic or personal attribute attached to a mention."""

    model_config = ConfigDict(extra="forbid")

    name: AttrName
    value_text: str
    source: SourceRef | None = None


class Mention(BaseModel):
    """Extracted entity mention with provenance and normalization state."""

    model_config = ConfigDict(extra="forbid")

    mention_id: str
    case_id: str
    doc_id: str
    type: EntityType
    surface_text: str
    normalized_value: str | None = None
    normalization_status: NormalizationStatus = NormalizationStatus.NOT_APPLICABLE
    checks: list[ValidationCheck] = Field(default_factory=list)
    stated_role: StatedRole | None = None
    attributes: list[MentionAttribute] = Field(default_factory=list)
    origin: Origin
    ocr: OcrInfo | None = None
    identifier_trust: IdentifierTrust = IdentifierTrust.NOT_APPLICABLE
    confirmed_by: str | None = None
    review_flags: list[ReviewKind] = Field(default_factory=list)
    source: SourceRef

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class Relationship(BaseModel):
    """Directed relationship between two mentions."""

    model_config = ConfigDict(extra="forbid")

    rel_id: str
    case_id: str
    type: RelType
    subject_mention_id: str
    object_mention_id: str
    assertion: Assertion
    origin: Origin
    review_flags: list[ReviewKind] = Field(default_factory=list)
    source: SourceRef

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class EventTime(BaseModel):
    """Parsed time description with ambiguity tracking."""

    model_config = ConfigDict(extra="forbid")

    original_text: str
    normalized_iso: str | None = None
    timezone: str | None = None
    ambiguity: TimeAmbiguity = TimeAmbiguity.NONE
    notes: str | None = None


class EventParticipant(BaseModel):
    """Participant mention reference and role in an event."""

    model_config = ConfigDict(extra="forbid")

    mention_id: str
    role: str | None = None


class EventAmount(BaseModel):
    """Financial amount associated with an event."""

    model_config = ConfigDict(extra="forbid")

    value_text: str
    decimal: float | None = None
    currency: str | None = None


class Event(BaseModel):
    """Extracted event fact (incident, call, transaction, etc.)."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    case_id: str
    type: EventType
    description: str
    time: EventTime | None = None
    participants: list[EventParticipant] = Field(default_factory=list)
    location_mention_id: str | None = None
    amount: EventAmount | None = None
    origin: Origin
    review_flags: list[ReviewKind] = Field(default_factory=list)
    source: SourceRef

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class Aggregate(BaseModel):
    """Aggregated communication or transaction statistics from bulk tabular data."""

    model_config = ConfigDict(extra="forbid")

    aggregate_id: str
    case_id: str
    type: RelType  # CALLED or TRANSFERRED_TO
    subject_mention_id: str
    object_mention_id: str
    count: int
    total_duration_s: float | None = None
    total_amount: float | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    sample_sources: list[SourceRef] = Field(default_factory=list)
    events_file: str | None = None
    events_row_range: str | list[int] | tuple[int, int] | None = None

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)

    @field_validator("sample_sources")
    @classmethod
    def check_sample_sources_limit(cls, v: list[SourceRef]) -> list[SourceRef]:
        if len(v) > 20:
            raise ValueError("sample_sources must contain at most 20 SourceRef items")
        return v


class ReviewItem(BaseModel):
    """Actionable human review queue item."""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    case_id: str
    kind: ReviewKind
    target_ids: list[str] = Field(default_factory=list)
    detail: str
    status: ReviewItemStatus = ReviewItemStatus.OPEN
    resolution: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class Rejection(BaseModel):
    """Record of an LLM output item that failed quote verification or schema validation."""

    model_config = ConfigDict(extra="forbid")

    rejection_id: str
    case_id: str
    doc_id: str
    kind: RejectionKind
    reason: str
    model_item_excerpt: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)

    @field_validator("model_item_excerpt")
    @classmethod
    def check_excerpt_limit(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 200:
            raise ValueError("model_item_excerpt must be at most 200 characters")
        return v


class PageInfo(BaseModel):
    """Per-page extraction metadata for an ingested document."""

    model_config = ConfigDict(extra="forbid")

    page: int
    method: PageMethod
    chars: int
    warnings: list[str] = Field(default_factory=list)


class SheetInfo(BaseModel):
    """Spreadsheet sheet metadata."""

    model_config = ConfigDict(extra="forbid")

    name: str
    state: SheetState = SheetState.VISIBLE
    rows: int
    merged_ranges: list[str] = Field(default_factory=list)
    formula_cells: int = 0
    formula_missing_cache: int = 0


class DocumentRecord(BaseModel):
    """Ingested and processed document record."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    file_name: str
    file_sha256: str
    size_bytes: int
    detected_type: str
    status: DocumentStatus = DocumentStatus.PROCESSED
    pages: list[PageInfo] = Field(default_factory=list)
    row_count: int | None = None
    sheets: list[SheetInfo] | None = None
    chunk_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    case_id: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_optional_case_id(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_case_id(v)
        return v


class RunMeta(BaseModel):
    """Metadata for an execution run across pipeline stages."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    started_at: str
    finished_at: str | None = None
    pipeline_version: str
    schema_version: str = "1.0.0"
    prompt_version: str
    provider: str
    model: str
    temperature: float = 0.0
    ocr_engine: str
    ocr_version: str
    ocr_langs: list[str] | str = Field(default_factory=list)
    normalization_version: str
    resolver_version: str
    idempotency_key: str


class CaseResult(BaseModel):
    """Top-level pipeline output encapsulating all facts and review items for a case."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    case_id: str
    run: RunMeta
    state: JobState
    documents: list[DocumentRecord] = Field(default_factory=list)
    mentions: list[Mention] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    aggregates: list[Aggregate] = Field(default_factory=list)
    review_items: list[ReviewItem] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class Signal(BaseModel):
    """Evidence signal supporting or contradicting an entity resolution suggestion."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    polarity: SignalPolarity
    detail: str
    sources: list[SourceRef] = Field(default_factory=list)


class ResolutionSuggestion(BaseModel):
    """Suggestion-only match candidate between mention and entity candidate."""

    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    case_id: str
    mention_id: str
    candidate_entity_id: str
    candidate_case_id: str | None = None
    status: SuggestionStatus
    heuristic_rank: float | None = None
    rank_note: str = "heuristic ordering, not a probability"
    signals: list[Signal] = Field(default_factory=list)
    explanation: str
    requires_human_decision: bool = True

    @field_validator("case_id")
    @classmethod
    def validate_case_id_field(cls, v: str) -> str:
        return validate_case_id(v)


class ReviewAction(BaseModel):
    """Persisted, hash-chained review decision performed by an authorized human."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    type: ReviewActionType
    actor: str
    at: str
    reason: str
    target_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    prev_hash: str
    entry_hash: str
    case_id: str | None = None

    @field_validator("case_id")
    @classmethod
    def validate_optional_case_id(cls, v: str | None) -> str | None:
        if v is not None:
            return validate_case_id(v)
        return v


__all__ = [
    "Aggregate",
    "CaseResult",
    "DocumentRecord",
    "Event",
    "EventAmount",
    "EventParticipant",
    "EventTime",
    "Mention",
    "MentionAttribute",
    "OcrInfo",
    "PageInfo",
    "Rejection",
    "Relationship",
    "ResolutionSuggestion",
    "ReviewAction",
    "ReviewItem",
    "RunMeta",
    "SheetInfo",
    "Signal",
    "SourceRef",
    "ValidationCheck",
]
