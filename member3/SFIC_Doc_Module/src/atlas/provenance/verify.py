"""Core quote verification and source provenance calculation for LLM extraction responses.

Implements Section 5.4 Quote verification algorithm:
1. Strict unit matching and document scoping.
2. Character length (>= 3 chars) and normalized substring verification.
3. Single hit -> verified; multiple hits -> verified_ambiguous_location + review flag.
4. Value-in-quote checks for all entity types (digit/alnum comparisons for identifiers).
5. Role keyword checks with downgrade to 'unknown' + role_inferred review item.
6. Local_id resolution enforcing endpoint presence.
7. Identifier trust routing: OCR-derived identifiers flagged for review.
8. Extra fields schema violation detection.
9. Deterministic ID generation using atlas.contracts.ids.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from atlas.contracts.enums import (
    Assertion,
    AttrName,
    EntityType,
    EventType,
    IdentifierTrust,
    NormalizationStatus,
    Origin,
    QuoteStatus,
    RejectionKind,
    RelType,
    ReviewKind,
    StatedRole,
    UnitKind,
)
from atlas.contracts.ids import (
    make_event_id,
    make_mention_id,
    make_rejection_id,
    make_rel_id,
    make_review_id,
    validate_case_id,
)
from atlas.contracts.records import (
    Event,
    EventParticipant,
    EventTime,
    Mention,
    MentionAttribute,
    Rejection,
    Relationship,
    ReviewItem,
    SourceRef,
)
from atlas.extract.units import Unit
from atlas.normalize.identifiers import (
    detect_identifiers,
    normalize_account,
    normalize_phone,
    normalize_vehicle,
    validate_imei,
)
from atlas.normalize.names import is_valid_person_name
from atlas.provenance.locate import find_all_occurrences, locate_quote_in_unit
from atlas.provenance.normalize_text import normalize_for_match

# Allowed fields per model output schema
_MENTION_ALLOWED_FIELDS = {"local_id", "type", "surface_text", "role_stated", "unit_id", "quote", "attributes"}
_ATTRIBUTE_ALLOWED_FIELDS = {"name", "value_text", "quote"}
_RELATIONSHIP_ALLOWED_FIELDS = {"type", "subject_local_id", "object_local_id", "unit_id", "quote"}
_EVENT_ALLOWED_FIELDS = {
    "type",
    "description",
    "time_text",
    "participant_local_ids",
    "location_local_id",
    "unit_id",
    "quote",
}

_DEFAULT_ROLE_KEYWORDS: dict[str, list[str]] = {
    "accused": ["accused", "आरोपी"],
    "suspect": ["suspect", "संदिग्ध"],
    "complainant": ["complainant", "शिकायतकर्ता"],
    "witness": ["witness", "गवाह"],
    "victim": ["victim", "पीड़ित"],
    "officer": ["officer", "io", "investigating officer", "अधिकारी"],
}


def _load_default_role_keywords() -> dict[str, list[str]]:
    """Load role keywords from config/role_keywords.yaml if available, else return defaults."""
    cfg_path = Path("config/role_keywords.yaml")
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return {
                        str(k).lower(): [str(item).lower() for item in v]
                        for k, v in data.items()
                        if isinstance(v, list)
                    }
        except Exception:
            pass
    return _DEFAULT_ROLE_KEYWORDS


def _map_method_to_origin(method: str) -> Origin:
    """Map unit extraction method string to Origin enum."""
    m = method.lower()
    if m in ("pdf_text",):
        return Origin.PDF_TEXT
    if m in ("ocr", "image_ocr"):
        return Origin.OCR
    if m in ("table", "table_parser"):
        return Origin.TABLE_PARSER
    if m in ("text", "text_file"):
        return Origin.TEXT_FILE
    if m in ("json", "json_file"):
        return Origin.JSON_FILE
    return Origin.PDF_TEXT


def _determine_unit_kind(unit_id: str) -> UnitKind:
    """Determine UnitKind from unit_id naming conventions."""
    if ":s" in unit_id and ":r" in unit_id:
        return UnitKind.ROW
    if ":j:" in unit_id:
        return UnitKind.FIELD
    if ":p" in unit_id and ":l" not in unit_id:
        return UnitKind.PAGE
    if ":l" in unit_id:
        return UnitKind.LINE
    return UnitKind.PAGE


def resolve_unit_id(raw_unit_id: str, units_by_id: Mapping[str, Unit], doc_id: str) -> str | None:
    """Resolve a model-reported unit reference to the exact unit inside this chunk.

    Live models frequently echo only the trailing segment of the ``[UNIT ...]`` header
    (for example ``l000005`` instead of ``DOC-ab12cd34ef56:p001:l000005``). Resolution is
    deterministic and performed strictly against the units that are actually present in
    this chunk, so a citation can never point anywhere the model was not shown:

    1. An exact ``unit_id`` match wins (and must belong to ``doc_id``).
    2. Otherwise a reference that is a unique ``:<segment>`` suffix of exactly one chunk
       unit is accepted.
    3. If the reference matches nothing, more than one unit, or a unit from another
       document, ``None`` is returned and the item is rejected. No identifier is invented.
    """
    if not raw_unit_id:
        return None

    exact = units_by_id.get(raw_unit_id)
    if exact is not None:
        if exact.doc_id and exact.doc_id != doc_id:
            return None
        if not raw_unit_id.startswith(doc_id):
            return None
        return raw_unit_id

    suffix = raw_unit_id if raw_unit_id.startswith(":") else f":{raw_unit_id}"
    matches = sorted(uid for uid in units_by_id if uid.startswith(doc_id) and uid.endswith(suffix))
    if len(matches) == 1:
        return matches[0]
    return None


def verify_model_output(
    model_output: dict[str, Any],
    chunk_units: list[Unit],
    case_id: str,
    doc_id: str,
    role_keywords: dict[str, list[str]] | None = None,
    ocr_pages: dict[int, Any] | None = None,
    file_name: str = "",
    file_sha256: str = "",
) -> tuple[list[Mention], list[Relationship], list[Event], list[ReviewItem], list[Rejection]]:
    """Verify raw LLM extraction output against chunk units and build evidence records.

    Args:
        model_output: Raw dictionary output returned by the LLM client.
        chunk_units: List of Unit objects present in the current prompt chunk.
        case_id: Case identifier matching regex ^[A-Za-z0-9_-]{1,64}$.
        doc_id: Document identifier matching doc_id of current units.
        role_keywords: Optional keyword dictionary mapping stated roles to matching keywords.
        ocr_pages: Optional dictionary mapping 1-indexed page numbers to OCR page results.
        file_name: Original file name.
        file_sha256: Original file SHA-256 hash.

    Returns:
        tuple containing:
        - list of verified Mention objects
        - list of verified Relationship objects
        - list of verified Event objects
        - list of actionable ReviewItem objects
        - list of Rejection objects
    """
    validate_case_id(case_id)

    if role_keywords is None:
        role_keywords = _load_default_role_keywords()

    # Fallback default file name and sha256
    effective_file_name = file_name or f"{doc_id}.pdf"
    effective_file_sha256 = file_sha256 or (doc_id[4:] if doc_id.startswith("DOC-") else "0" * 64)

    units_by_id: dict[str, Unit] = {u.unit_id: u for u in chunk_units}
    norm_unit_texts: dict[str, str] = {u.unit_id: normalize_for_match(u.text) for u in chunk_units}

    verified_mentions: dict[str, Mention] = {}
    mentions_list: list[Mention] = []
    relationships_list: list[Relationship] = []
    events_list: list[Event] = []
    review_items_list: list[ReviewItem] = []
    rejections_list: list[Rejection] = []

    rejection_counter = 0

    def add_rejection(kind: RejectionKind, reason: str, excerpt: str | None = None) -> None:
        nonlocal rejection_counter
        rejection_counter += 1
        rejection_id = make_rejection_id(case_id, doc_id, kind.value, reason, rejection_counter)
        rejections_list.append(
            Rejection(
                rejection_id=rejection_id,
                case_id=case_id,
                doc_id=doc_id,
                kind=kind,
                reason=reason,
                model_item_excerpt=excerpt[:200] if excerpt else None,
            )
        )

    # -------------------------------------------------------------------------
    # 1. Mentions verification
    # -------------------------------------------------------------------------
    raw_mentions = model_output.get("mentions", [])
    if not isinstance(raw_mentions, list):
        add_rejection(RejectionKind.SCHEMA_VIOLATION, "mentions field must be a list", str(raw_mentions))
        raw_mentions = []

    mention_occurrence_tracker: dict[str, int] = {}

    for raw_m in raw_mentions:
        if not isinstance(raw_m, dict):
            add_rejection(RejectionKind.SCHEMA_VIOLATION, "Mention item must be a dictionary", str(raw_m))
            continue

        # Check for unknown extra fields in mention
        extra_m_keys = set(raw_m.keys()) - _MENTION_ALLOWED_FIELDS
        if extra_m_keys:
            add_rejection(
                RejectionKind.SCHEMA_VIOLATION,
                f"Unexpected extra fields in mention: {sorted(extra_m_keys)}",
                str(raw_m),
            )
            continue

        local_id = str(raw_m.get("local_id", "")).strip()
        type_str = str(raw_m.get("type", "")).strip()
        surface_text = str(raw_m.get("surface_text", "")).strip()
        raw_unit_id = str(raw_m.get("unit_id", "")).strip()
        quote = str(raw_m.get("quote", "")).strip()

        # Check unit validity (accept a unique abbreviated reference to a chunk unit)
        resolved_unit_id = resolve_unit_id(raw_unit_id, units_by_id, doc_id)
        if resolved_unit_id is None:
            add_rejection(
                RejectionKind.UNIT_NOT_IN_CHUNK,
                f"Unit '{raw_unit_id}' not found in current chunk or does not match doc_id '{doc_id}'",
                str(raw_m),
            )
            continue

        unit_id = resolved_unit_id
        unit = units_by_id[unit_id]
        if unit.doc_id and unit.doc_id != doc_id:
            add_rejection(
                RejectionKind.UNIT_NOT_IN_CHUNK,
                f"Unit '{unit_id}' doc_id '{unit.doc_id}' does not match document '{doc_id}'",
                str(raw_m),
            )
            continue

        # Check quote length
        if len(quote) < 3:
            add_rejection(
                RejectionKind.QUOTE_NOT_FOUND,
                f"Quote too short (< 3 characters): '{quote}'",
                str(raw_m),
            )
            continue

        # Substring search in normalized unit text
        norm_quote = normalize_for_match(quote)
        norm_page = norm_unit_texts[unit_id]
        hits = find_all_occurrences(norm_quote, norm_page)

        if len(hits) == 0:
            add_rejection(
                RejectionKind.QUOTE_NOT_FOUND,
                f"Quote '{quote}' not found in unit '{unit_id}'",
                str(raw_m),
            )
            continue

        quote_status = QuoteStatus.VERIFIED if len(hits) == 1 else QuoteStatus.VERIFIED_AMBIGUOUS_LOCATION

        # Value-in-quote check
        val_in_quote = False
        norm_surface = normalize_for_match(surface_text)

        if type_str in (EntityType.PHONE.value, EntityType.IMEI.value, EntityType.ACCOUNT.value):
            digits_surface = re.sub(r"\D", "", surface_text)
            digits_quote = re.sub(r"\D", "", quote)
            val_in_quote = digits_surface in digits_quote if digits_surface else norm_surface in norm_quote
        elif type_str == EntityType.VEHICLE.value:
            alnum_surface = re.sub(r"[^A-Za-z0-9]", "", surface_text).upper()
            alnum_quote = re.sub(r"[^A-Za-z0-9]", "", quote).upper()
            val_in_quote = alnum_surface in alnum_quote if alnum_surface else norm_surface in norm_quote
        else:
            val_in_quote = norm_surface in norm_quote

        if not val_in_quote:
            add_rejection(
                RejectionKind.VALUE_NOT_IN_QUOTE,
                f"surface_text '{surface_text}' not found in quote '{quote}'",
                str(raw_m),
            )
            continue

        if type_str == EntityType.PERSON.value and not is_valid_person_name(surface_text):
            add_rejection(
                RejectionKind.SCHEMA_VIOLATION,
                f"Invalid person surface_text: '{surface_text}' is a generic phrase or placeholder, not a named person",
                str(raw_m),
            )
            continue

        # Locate line and bbox
        ocr_page = ocr_pages.get(unit.page) if (ocr_pages and unit.page) else None
        line_start, line_end, bbox = locate_quote_in_unit(unit, quote, 0, ocr_page)
        text_origin = _map_method_to_origin(unit.method)
        unit_kind = _determine_unit_kind(unit_id)

        source_ref = SourceRef(
            doc_id=doc_id,
            file_name=effective_file_name,
            file_sha256=effective_file_sha256,
            unit_id=unit_id,
            unit_kind=unit_kind,
            page=unit.page,
            sheet=None,
            row=None,
            line_start=line_start,
            line_end=line_end,
            bbox=bbox,
            text_origin=text_origin,
            quote=quote,
            quote_status=quote_status,
            occurrence_count=len(hits),
        )

        review_flags: list[ReviewKind] = []
        pending_review_items: list[tuple[ReviewKind, str]] = []

        if quote_status == QuoteStatus.VERIFIED_AMBIGUOUS_LOCATION:
            review_flags.append(ReviewKind.AMBIGUOUS_LOCATION)
            pending_review_items.append(
                (ReviewKind.AMBIGUOUS_LOCATION, f"Quote appears {len(hits)} times in unit {unit_id}")
            )

        # Role verification
        raw_role = raw_m.get("role_stated")
        stated_role: StatedRole | None = None
        if raw_role:
            role_lower = str(raw_role).lower().strip()
            if role_lower in ("accused", "suspect", "complainant", "witness", "victim", "officer"):
                kw_list = role_keywords.get(role_lower, [])
                has_kw = any(kw in quote.lower() for kw in kw_list)
                if has_kw:
                    stated_role = StatedRole(role_lower)
                else:
                    stated_role = StatedRole.UNKNOWN
                    review_flags.append(ReviewKind.ROLE_INFERRED)
                    pending_review_items.append(
                        (
                            ReviewKind.ROLE_INFERRED,
                            f"Stated role '{role_lower}' missing required keyword in quote; downgraded to unknown",
                        )
                    )
            else:
                try:
                    stated_role = StatedRole(role_lower)
                except ValueError:
                    stated_role = StatedRole.UNKNOWN

        # Identifier normalization and trust
        normalized_value: str | None = None
        normalization_status = NormalizationStatus.NOT_APPLICABLE
        identifier_trust = IdentifierTrust.NOT_APPLICABLE

        if type_str == EntityType.PHONE.value:
            norm_val, stat = normalize_phone(surface_text)
            normalized_value = norm_val
            normalization_status = NormalizationStatus(stat)
        elif type_str == EntityType.IMEI.value:
            norm_val, stat = validate_imei(surface_text)
            normalized_value = norm_val
            normalization_status = NormalizationStatus(stat)
        elif type_str == EntityType.VEHICLE.value:
            norm_val, stat = normalize_vehicle(surface_text)
            normalized_value = norm_val
            if stat == "ok":
                normalization_status = NormalizationStatus.OK
            elif stat == "format_unrecognized":
                normalization_status = NormalizationStatus.AMBIGUOUS
            else:
                normalization_status = NormalizationStatus(stat)
        elif type_str == EntityType.ACCOUNT.value:
            norm_val, stat = normalize_account(surface_text)
            normalized_value = norm_val
            normalization_status = NormalizationStatus(stat)

        # Identifier trust assignment
        if type_str in (
            EntityType.PHONE.value,
            EntityType.IMEI.value,
            EntityType.VEHICLE.value,
            EntityType.ACCOUNT.value,
        ):
            if normalization_status in (NormalizationStatus.INVALID, NormalizationStatus.AMBIGUOUS):
                identifier_trust = IdentifierTrust.BLOCKED
                review_flags.append(ReviewKind.INVALID_IDENTIFIER)
                pending_review_items.append(
                    (ReviewKind.INVALID_IDENTIFIER, f"Identifier failed validation: {surface_text}")
                )
            elif normalization_status == NormalizationStatus.MASKED:
                identifier_trust = IdentifierTrust.BLOCKED
            else:
                # Normalization is OK: verify against deterministic candidates
                candidates = detect_identifiers(unit.text)
                matched_cand = False
                for c in candidates:
                    if c["type"] == type_str:
                        if c.get("normalized_value") and c["normalized_value"] == normalized_value:
                            matched_cand = True
                            break
                        if c.get("raw_text") and (
                            re.sub(r"\D", "", c["raw_text"]) == re.sub(r"\D", "", surface_text)
                            or c["raw_text"].strip() == surface_text.strip()
                        ):
                            matched_cand = True
                            break

                if not matched_cand:
                    identifier_trust = IdentifierTrust.BLOCKED
                    review_flags.append(ReviewKind.IDENTIFIER_NOT_FOUND_BY_PARSER)
                    pending_review_items.append(
                        (
                            ReviewKind.IDENTIFIER_NOT_FOUND_BY_PARSER,
                            f"Identifier '{surface_text}' was not confirmed by deterministic parser in {unit_id}",
                        )
                    )
                elif text_origin == Origin.OCR:
                    identifier_trust = IdentifierTrust.REVIEW_REQUIRED
                    review_flags.append(ReviewKind.LOW_TRUST_IDENTIFIER)
                    pending_review_items.append(
                        (
                            ReviewKind.LOW_TRUST_IDENTIFIER,
                            f"Identifier '{surface_text}' originates from OCR text and requires human confirmation",
                        )
                    )
                else:
                    identifier_trust = IdentifierTrust.STRONG

        # Parse attributes
        attributes: list[MentionAttribute] = []
        raw_attrs = raw_m.get("attributes", [])
        if isinstance(raw_attrs, list):
            for raw_attr in raw_attrs:
                if not isinstance(raw_attr, dict):
                    continue
                # Check extra fields in attribute
                if set(raw_attr.keys()) - _ATTRIBUTE_ALLOWED_FIELDS:
                    continue
                attr_name = str(raw_attr.get("name", ""))
                attr_val = str(raw_attr.get("value_text", ""))
                attr_quote = str(raw_attr.get("quote", ""))

                # Verify attribute quote in unit if present
                attr_source: SourceRef | None = None
                if len(attr_quote) >= 3:
                    norm_aq = normalize_for_match(attr_quote)
                    if norm_aq in norm_page:
                        a_start, a_end, a_bbox = locate_quote_in_unit(unit, attr_quote, 0, ocr_page)
                        attr_source = SourceRef(
                            doc_id=doc_id,
                            file_name=effective_file_name,
                            file_sha256=effective_file_sha256,
                            unit_id=unit_id,
                            unit_kind=unit_kind,
                            page=unit.page,
                            line_start=a_start,
                            line_end=a_end,
                            bbox=a_bbox,
                            text_origin=text_origin,
                            quote=attr_quote,
                            quote_status=QuoteStatus.VERIFIED,
                            occurrence_count=1,
                        )

                try:
                    name_enum = AttrName(attr_name)
                    attributes.append(MentionAttribute(name=name_enum, value_text=attr_val, source=attr_source))
                except ValueError:
                    continue

        # Compute occurrence index for mention_id
        occ_key = f"{doc_id}|{unit_id}|{type_str}|{normalized_value or surface_text}"
        occurrence_idx = mention_occurrence_tracker.get(occ_key, 0)
        mention_occurrence_tracker[occ_key] = occurrence_idx + 1

        mention_id = make_mention_id(
            doc_id=doc_id,
            unit_id=unit_id,
            type_str=type_str,
            normalized_or_surface=normalized_value or surface_text,
            occurrence_index=occurrence_idx,
        )

        try:
            entity_type_enum = EntityType(type_str)
        except ValueError:
            add_rejection(RejectionKind.SCHEMA_VIOLATION, f"Unknown entity type: '{type_str}'", str(raw_m))
            continue

        mention = Mention(
            mention_id=mention_id,
            case_id=case_id,
            doc_id=doc_id,
            type=entity_type_enum,
            surface_text=surface_text,
            normalized_value=normalized_value,
            normalization_status=normalization_status,
            checks=[],
            stated_role=stated_role,
            attributes=attributes,
            origin=text_origin,
            ocr=None,
            identifier_trust=identifier_trust,
            confirmed_by=None,
            review_flags=review_flags,
            source=source_ref,
        )

        # Emit review items for this mention
        for rev_kind, rev_detail in pending_review_items:
            review_id = make_review_id(case_id, rev_kind.value, mention_id, rev_detail)
            review_items_list.append(
                ReviewItem(
                    review_id=review_id,
                    case_id=case_id,
                    kind=rev_kind,
                    target_ids=[mention_id],
                    detail=rev_detail,
                )
            )

        verified_mentions[local_id] = mention
        mentions_list.append(mention)

    # -------------------------------------------------------------------------
    # 2. Relationships verification
    # -------------------------------------------------------------------------
    raw_relationships = model_output.get("relationships", [])
    if isinstance(raw_relationships, list):
        rel_occurrence_tracker: dict[str, int] = {}
        for raw_r in raw_relationships:
            if not isinstance(raw_r, dict):
                add_rejection(RejectionKind.SCHEMA_VIOLATION, "Relationship must be a dictionary", str(raw_r))
                continue

            extra_r_keys = set(raw_r.keys()) - _RELATIONSHIP_ALLOWED_FIELDS
            if extra_r_keys:
                add_rejection(
                    RejectionKind.SCHEMA_VIOLATION,
                    f"Unexpected extra fields in relationship: {sorted(extra_r_keys)}",
                    str(raw_r),
                )
                continue

            rel_type_str = str(raw_r.get("type", "")).strip()
            subj_local = str(raw_r.get("subject_local_id", "")).strip()
            obj_local = str(raw_r.get("object_local_id", "")).strip()
            raw_unit_id = str(raw_r.get("unit_id", "")).strip()
            quote = str(raw_r.get("quote", "")).strip()

            # Local ID resolution
            if subj_local not in verified_mentions or obj_local not in verified_mentions:
                add_rejection(
                    RejectionKind.UNKNOWN_LOCAL_ID,
                    f"Relationship references unknown local_id: subject='{subj_local}', object='{obj_local}'",
                    str(raw_r),
                )
                continue

            subj_mention = verified_mentions[subj_local]
            obj_mention = verified_mentions[obj_local]

            # Unit verification (accept a unique abbreviated reference to a chunk unit)
            resolved_unit_id = resolve_unit_id(raw_unit_id, units_by_id, doc_id)
            if resolved_unit_id is None:
                add_rejection(
                    RejectionKind.UNIT_NOT_IN_CHUNK,
                    f"Unit '{raw_unit_id}' not found in current chunk",
                    str(raw_r),
                )
                continue

            unit_id = resolved_unit_id
            unit = units_by_id[unit_id]
            if len(quote) < 3:
                add_rejection(
                    RejectionKind.QUOTE_NOT_FOUND,
                    f"Relationship quote too short (< 3 chars): '{quote}'",
                    str(raw_r),
                )
                continue

            norm_quote = normalize_for_match(quote)
            norm_page = norm_unit_texts[unit_id]
            hits = find_all_occurrences(norm_quote, norm_page)
            if len(hits) == 0:
                add_rejection(
                    RejectionKind.QUOTE_NOT_FOUND,
                    f"Relationship quote not found in unit '{unit_id}'",
                    str(raw_r),
                )
                continue

            ocr_page = ocr_pages.get(unit.page) if (ocr_pages and unit.page) else None
            line_start, line_end, bbox = locate_quote_in_unit(unit, quote, 0, ocr_page)
            text_origin = _map_method_to_origin(unit.method)
            unit_kind = _determine_unit_kind(unit_id)

            source_ref = SourceRef(
                doc_id=doc_id,
                file_name=effective_file_name,
                file_sha256=effective_file_sha256,
                unit_id=unit_id,
                unit_kind=unit_kind,
                page=unit.page,
                line_start=line_start,
                line_end=line_end,
                bbox=bbox,
                text_origin=text_origin,
                quote=quote,
                quote_status=QuoteStatus.VERIFIED if len(hits) == 1 else QuoteStatus.VERIFIED_AMBIGUOUS_LOCATION,
                occurrence_count=len(hits),
            )

            # Stated vs model_inferred check
            subj_in = normalize_for_match(subj_mention.surface_text) in norm_quote
            obj_in = normalize_for_match(obj_mention.surface_text) in norm_quote
            rel_review_flags: list[ReviewKind] = []

            if subj_in and obj_in:
                assertion = Assertion.STATED
            else:
                assertion = Assertion.MODEL_INFERRED
                rel_review_flags.append(ReviewKind.ROLE_INFERRED)

            occ_key = f"{doc_id}|{unit_id}|{rel_type_str}|{subj_mention.mention_id}|{obj_mention.mention_id}"
            occurrence_idx = rel_occurrence_tracker.get(occ_key, 0)
            rel_occurrence_tracker[occ_key] = occurrence_idx + 1

            rel_id = make_rel_id(
                doc_id=doc_id,
                unit_id=unit_id,
                type_str=rel_type_str,
                subject_mention_id=subj_mention.mention_id,
                object_mention_id=obj_mention.mention_id,
                occurrence_index=occurrence_idx,
            )

            if assertion == Assertion.MODEL_INFERRED:
                detail = (
                    f"Relationship {rel_type_str} between {subj_local} and {obj_local} not explicitly stated in quote"
                )
                rev_id = make_review_id(case_id, ReviewKind.ROLE_INFERRED.value, rel_id, detail)
                review_items_list.append(
                    ReviewItem(
                        review_id=rev_id,
                        case_id=case_id,
                        kind=ReviewKind.ROLE_INFERRED,
                        target_ids=[rel_id],
                        detail=detail,
                    )
                )

            try:
                rel_type_enum = RelType(rel_type_str)
                relationships_list.append(
                    Relationship(
                        rel_id=rel_id,
                        case_id=case_id,
                        type=rel_type_enum,
                        subject_mention_id=subj_mention.mention_id,
                        object_mention_id=obj_mention.mention_id,
                        assertion=assertion,
                        origin=text_origin,
                        review_flags=rel_review_flags,
                        source=source_ref,
                    )
                )
            except ValueError:
                add_rejection(
                    RejectionKind.SCHEMA_VIOLATION, f"Unknown relationship type: '{rel_type_str}'", str(raw_r)
                )

    # -------------------------------------------------------------------------
    # 3. Events verification
    # -------------------------------------------------------------------------
    raw_events = model_output.get("events", [])
    if isinstance(raw_events, list):
        event_occurrence_tracker: dict[str, int] = {}
        for raw_e in raw_events:
            if not isinstance(raw_e, dict):
                add_rejection(RejectionKind.SCHEMA_VIOLATION, "Event must be a dictionary", str(raw_e))
                continue

            extra_e_keys = set(raw_e.keys()) - _EVENT_ALLOWED_FIELDS
            if extra_e_keys:
                add_rejection(
                    RejectionKind.SCHEMA_VIOLATION,
                    f"Unexpected extra fields in event: {sorted(extra_e_keys)}",
                    str(raw_e),
                )
                continue

            event_type_str = str(raw_e.get("type", "")).strip()
            description = str(raw_e.get("description", "")).strip()
            time_text = raw_e.get("time_text")
            participant_ids = raw_e.get("participant_local_ids", [])
            location_id = raw_e.get("location_local_id")
            raw_unit_id = str(raw_e.get("unit_id", "")).strip()
            quote = str(raw_e.get("quote", "")).strip()

            # Participant & location local_id check
            unknown_pids = [pid for pid in participant_ids if pid not in verified_mentions]
            if unknown_pids or (location_id and location_id not in verified_mentions):
                add_rejection(
                    RejectionKind.UNKNOWN_LOCAL_ID,
                    f"Event references unknown local_id(s): participants={unknown_pids}, location={location_id}",
                    str(raw_e),
                )
                continue

            # Unit verification (accept a unique abbreviated reference to a chunk unit)
            resolved_unit_id = resolve_unit_id(raw_unit_id, units_by_id, doc_id)
            if resolved_unit_id is None:
                add_rejection(
                    RejectionKind.UNIT_NOT_IN_CHUNK,
                    f"Event unit '{raw_unit_id}' not found in current chunk",
                    str(raw_e),
                )
                continue

            unit_id = resolved_unit_id
            unit = units_by_id[unit_id]
            if len(quote) < 3:
                add_rejection(
                    RejectionKind.QUOTE_NOT_FOUND,
                    f"Event quote too short (< 3 chars): '{quote}'",
                    str(raw_e),
                )
                continue

            norm_quote = normalize_for_match(quote)
            norm_page = norm_unit_texts[unit_id]
            hits = find_all_occurrences(norm_quote, norm_page)
            if len(hits) == 0:
                add_rejection(
                    RejectionKind.QUOTE_NOT_FOUND,
                    f"Event quote not found in unit '{unit_id}'",
                    str(raw_e),
                )
                continue

            ocr_page = ocr_pages.get(unit.page) if (ocr_pages and unit.page) else None
            line_start, line_end, bbox = locate_quote_in_unit(unit, quote, 0, ocr_page)
            text_origin = _map_method_to_origin(unit.method)
            unit_kind = _determine_unit_kind(unit_id)

            source_ref = SourceRef(
                doc_id=doc_id,
                file_name=effective_file_name,
                file_sha256=effective_file_sha256,
                unit_id=unit_id,
                unit_kind=unit_kind,
                page=unit.page,
                line_start=line_start,
                line_end=line_end,
                bbox=bbox,
                text_origin=text_origin,
                quote=quote,
                quote_status=QuoteStatus.VERIFIED if len(hits) == 1 else QuoteStatus.VERIFIED_AMBIGUOUS_LOCATION,
                occurrence_count=len(hits),
            )

            occ_key = f"{doc_id}|{unit_id}|{event_type_str}|{description}"
            occurrence_idx = event_occurrence_tracker.get(occ_key, 0)
            event_occurrence_tracker[occ_key] = occurrence_idx + 1

            event_id = make_event_id(
                doc_id=doc_id,
                unit_id=unit_id,
                type_str=event_type_str,
                description_or_time=description,
                occurrence_index=occurrence_idx,
            )

            participants = [
                EventParticipant(mention_id=verified_mentions[pid].mention_id)
                for pid in participant_ids
                if pid in verified_mentions
            ]
            loc_mention_id = verified_mentions[location_id].mention_id if location_id else None

            event_time = EventTime(original_text=time_text) if time_text else None

            try:
                event_type_enum = EventType(event_type_str)
                events_list.append(
                    Event(
                        event_id=event_id,
                        case_id=case_id,
                        type=event_type_enum,
                        description=description,
                        time=event_time,
                        participants=participants,
                        location_mention_id=loc_mention_id,
                        amount=None,
                        origin=text_origin,
                        review_flags=[],
                        source=source_ref,
                    )
                )
            except ValueError:
                add_rejection(RejectionKind.SCHEMA_VIOLATION, f"Unknown event type: '{event_type_str}'", str(raw_e))

    return mentions_list, relationships_list, events_list, review_items_list, rejections_list


__all__ = ["resolve_unit_id", "verify_model_output"]
