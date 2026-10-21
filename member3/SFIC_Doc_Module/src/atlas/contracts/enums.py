"""Domain enums for ATLAS Dev 3 contracts.

All enums use the (str, Enum) pattern for seamless JSON serialization
and Pydantic v2 compatibility.
"""

from __future__ import annotations

from enum import StrEnum


class EntityType(StrEnum):
    """Supported entity categories extracted from evidence documents."""

    PERSON = "PERSON"
    PHONE = "PHONE"
    IMEI = "IMEI"
    VEHICLE = "VEHICLE"
    ACCOUNT = "ACCOUNT"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"


class StatedRole(StrEnum):
    """Stated role for PERSON entities in narrative police documents."""

    COMPLAINANT = "complainant"
    ACCUSED = "accused"
    SUSPECT = "suspect"
    WITNESS = "witness"
    VICTIM = "victim"
    OFFICER = "officer"
    OTHER = "other"
    UNKNOWN = "unknown"


class RelType(StrEnum):
    """Relationship categories linking mentions or entities."""

    USES_PHONE = "USES_PHONE"
    USES_DEVICE = "USES_DEVICE"
    OWNS_VEHICLE = "OWNS_VEHICLE"
    HOLDS_ACCOUNT = "HOLDS_ACCOUNT"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    EMPLOYED_BY = "EMPLOYED_BY"
    LOCATED_AT = "LOCATED_AT"
    ALSO_KNOWN_AS = "ALSO_KNOWN_AS"
    CALLED = "CALLED"
    TRANSFERRED_TO = "TRANSFERRED_TO"


class EventType(StrEnum):
    """Event types extracted from narrative or tabular records."""

    INCIDENT = "INCIDENT"
    CALL = "CALL"
    TRANSACTION = "TRANSACTION"
    MEETING = "MEETING"
    ARREST = "ARREST"
    SIGHTING = "SIGHTING"
    OTHER = "OTHER"


class Origin(StrEnum):
    """Origin mechanism indicating how text or fact was derived."""

    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    TABLE_PARSER = "table_parser"
    TEXT_FILE = "text_file"
    JSON_FILE = "json_file"
    MODEL_INFERRED = "model_inferred"


class Assertion(StrEnum):
    """Assertion confidence grade for relationships and facts."""

    STATED = "stated"
    MODEL_INFERRED = "model_inferred"
    STRUCTURED_RECORD = "structured_record"


class AttrName(StrEnum):
    """Standardized demographic and personal attribute names."""

    FATHER_NAME = "father_name"
    AGE = "age"
    DOB = "dob"
    GENDER = "gender"
    ADDRESS = "address"
    OCCUPATION = "occupation"


class JobState(StrEnum):
    """Job execution states for document processing."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    FAILED_VALIDATION = "failed_validation"
    REJECTED_INPUT = "rejected_input"


class ReviewKind(StrEnum):
    """Categorized review triggers requiring human reviewer inspection."""

    LOW_TRUST_IDENTIFIER = "low_trust_identifier"
    INVALID_IDENTIFIER = "invalid_identifier"
    IDENTIFIER_NOT_FOUND_BY_PARSER = "identifier_not_found_by_parser"
    ROLE_INFERRED = "role_inferred"
    AMBIGUOUS_DATE = "ambiguous_date"
    CONTRADICTION = "contradiction"
    AMBIGUOUS_LOCATION = "ambiguous_location"
    MAPPING_UNCONFIRMED = "mapping_unconfirmed"
    TABULAR_PDF_DETECTED = "tabular_pdf_detected"
    MATCH_CANDIDATE = "match_candidate"
    CHUNK_FAILED = "chunk_failed"


class SuggestionStatus(StrEnum):
    """Categorization status for entity resolution suggestions."""

    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


class ReviewActionType(StrEnum):
    """Human review actions applied to review items and suggestions."""

    CONFIRM_IDENTIFIER = "CONFIRM_IDENTIFIER"
    CORRECT_IDENTIFIER = "CORRECT_IDENTIFIER"
    APPROVE_MATCH = "APPROVE_MATCH"
    REJECT_MATCH = "REJECT_MATCH"
    MERGE = "MERGE"
    SPLIT = "SPLIT"
    RESOLVE_ITEM = "RESOLVE_ITEM"


class UnitKind(StrEnum):
    """Type of reference unit in evidence documents."""

    PAGE = "page"
    LINE = "line"
    ROW = "row"
    FIELD = "field"


class QuoteStatus(StrEnum):
    """Verification outcome of quoted source text against document units."""

    VERIFIED = "verified"
    VERIFIED_AMBIGUOUS_LOCATION = "verified_ambiguous_location"
    UNVERIFIED = "unverified"


class OcrLevel(StrEnum):
    """Granularity level of OCR confidence scoring."""

    WORD = "word"
    LINE = "line"
    NONE = "none"


class NormalizationStatus(StrEnum):
    """Status of deterministic identifier/attribute normalization."""

    OK = "ok"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    MASKED = "masked"
    NOT_APPLICABLE = "not_applicable"


class IdentifierTrust(StrEnum):
    """Trust classification for identifiers governing graph node creation."""

    STRONG = "strong"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class TimeAmbiguity(StrEnum):
    """Date/time ambiguity classification."""

    NONE = "none"
    DMY_MDY = "dmy_mdy"
    PARTIAL = "partial"
    UNPARSEABLE = "unparseable"


class ReviewItemStatus(StrEnum):
    """Resolution lifecycle status for a review item."""

    OPEN = "open"
    RESOLVED = "resolved"


class RejectionKind(StrEnum):
    """Reason category for rejecting an LLM extraction item."""

    QUOTE_NOT_FOUND = "quote_not_found"
    UNIT_NOT_IN_CHUNK = "unit_not_in_chunk"
    VALUE_NOT_IN_QUOTE = "value_not_in_quote"
    SCHEMA_VIOLATION = "schema_violation"
    UNKNOWN_LOCAL_ID = "unknown_local_id"
    ROLE_UNSUPPORTED = "role_unsupported"


class DocumentStatus(StrEnum):
    """Processing status of an ingested evidence document."""

    PROCESSED = "processed"
    PARTIAL = "partial"
    REJECTED_INPUT = "rejected_input"
    FAILED = "failed"


class PageMethod(StrEnum):
    """Extraction method applied to a specific document page."""

    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    IMAGE_OCR = "image_ocr"
    TABLE = "table"
    TEXT = "text"


class SheetState(StrEnum):
    """Visibility state of a spreadsheet sheet."""

    VISIBLE = "visible"
    HIDDEN = "hidden"
    VERY_HIDDEN = "veryHidden"


class SignalPolarity(StrEnum):
    """Polarity of evidence signal in entity resolution."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


__all__ = [
    "Assertion",
    "AttrName",
    "DocumentStatus",
    "EntityType",
    "EventType",
    "IdentifierTrust",
    "JobState",
    "NormalizationStatus",
    "OcrLevel",
    "Origin",
    "PageMethod",
    "QuoteStatus",
    "RejectionKind",
    "RelType",
    "ReviewActionType",
    "ReviewItemStatus",
    "ReviewKind",
    "SheetState",
    "SignalPolarity",
    "StatedRole",
    "SuggestionStatus",
    "TimeAmbiguity",
    "UnitKind",
]
