"""ANPR CCTV camera detection parser for tabular evidence.

Parses ANPR records into Mention, Event, and ReviewItem objects.
- Extracts VEHICLE mentions for registration plates.
- Extracts LOCATION mentions for observation sites.
- Creates SIGHTING events with timing and location links.
- Emits review items for unresolved plates or low-confidence OCR.
"""

from __future__ import annotations

from typing import Any

from atlas.contracts.enums import (
    EntityType,
    EventType,
    IdentifierTrust,
    Origin,
    QuoteStatus,
    ReviewItemStatus,
    ReviewKind,
    UnitKind,
)
from atlas.contracts.ids import (
    make_event_id,
    make_mention_id,
    make_review_id,
    make_unit_id_row,
    validate_case_id,
)
from atlas.contracts.records import (
    Event,
    EventParticipant,
    EventTime,
    Mention,
    ReviewItem,
    SourceRef,
)
from atlas.normalize.identifiers import normalize_vehicle
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.profiles import create_mapping_unconfirmed_review


def parse_anpr(
    rows: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    case_id: str,
    doc_id: str,
    file_name: str | None = None,
    file_sha256: str | None = None,
    sheet_index: int = 0,
    sheet_name: str | None = None,
    review_items: list[ReviewItem] | None = None,
) -> tuple[list[Event], list[Any], list[Mention]]:
    """Parse ANPR rows into Events, Aggregates (empty), and Mentions."""
    validate_case_id(case_id)

    if profile is None:
        if review_items is not None:
            review_items.append(
                create_mapping_unconfirmed_review(
                    case_id=case_id,
                    doc_id=doc_id,
                    headers=[],
                    detail="No matching ANPR profile provided or confirmed.",
                )
            )
        return ([], [], [])

    fname = file_name or f"{doc_id}.xlsx"
    fsha = file_sha256 or (doc_id[4:].ljust(64, "0") if len(doc_id) > 4 else "0" * 64)

    aliases: dict[str, str] = profile.get("header_aliases", {})
    date_format: str | None = profile.get("date_format")
    tz: str | None = profile.get("timezone", "Asia/Kolkata")

    def get_val(row_vals: dict[str, Any], canonical_key: str) -> Any:
        if canonical_key in row_vals and row_vals[canonical_key] is not None:
            v = str(row_vals[canonical_key]).strip()
            if v != "":
                return row_vals[canonical_key]
        for alias, target in aliases.items():
            if target == canonical_key and alias in row_vals and row_vals[alias] is not None:
                v = str(row_vals[alias]).strip()
                if v != "":
                    return row_vals[alias]
        return None

    events: list[Event] = []
    mentions: list[Mention] = []

    for idx, row in enumerate(rows, start=2):
        row_num = row.get("row_num", idx)
        if row.get("is_blank", False):
            continue

        row_vals: dict[str, Any] = row.get("values", row)

        event_id_raw = get_val(row_vals, "event_id")
        camera_id = get_val(row_vals, "camera_id")
        plate_ocr = get_val(row_vals, "plate_ocr")
        plate_reviewed = get_val(row_vals, "plate_reviewed")
        site = get_val(row_vals, "site")
        timestamp_raw = get_val(row_vals, "timestamp") or get_val(row_vals, "source_time")
        ocr_conf = get_val(row_vals, "ocr_confidence")
        ocr_conf_val: float | None = None
        if ocr_conf is not None:
            try:
                ocr_conf_val = float(str(ocr_conf).strip())
            except ValueError:
                ocr_conf_val = None

        if not plate_ocr and not plate_reviewed:
            continue

        effective_plate = (
            plate_reviewed if (plate_reviewed and str(plate_reviewed).strip() != "UNRESOLVED") else plate_ocr
        )
        plate_str = str(effective_plate).strip() if effective_plate is not None else "UNKNOWN"
        norm_plate, _ = normalize_vehicle(plate_str)

        # Build SourceRef
        unit_id = make_unit_id_row(doc_id, sheet_index, row_num)
        quote = f"event_id={event_id_raw}, camera={camera_id}, plate={plate_str}, time={timestamp_raw}"

        source_ref = SourceRef(
            doc_id=doc_id,
            file_name=fname,
            file_sha256=fsha,
            unit_id=unit_id,
            unit_kind=UnitKind.ROW,
            sheet=sheet_name,
            row=row_num,
            text_origin=Origin.TABLE_PARSER,
            quote=quote,
            quote_status=QuoteStatus.VERIFIED,
            occurrence_count=1,
        )

        # Vehicle Mention
        v_m_id = make_mention_id(doc_id, unit_id, "VEHICLE", plate_str, "plate")
        is_trust_strong = plate_reviewed and str(plate_reviewed).strip() != "UNRESOLVED"
        mentions.append(
            Mention(
                mention_id=v_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.VEHICLE,
                surface_text=plate_str,
                normalized_value=norm_plate or plate_str,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG if is_trust_strong else IdentifierTrust.REVIEW_REQUIRED,
                source=source_ref,
            )
        )

        # Location Mention
        loc_m_id: str | None = None
        if site:
            site_str = str(site).strip()
            loc_m_id = make_mention_id(doc_id, unit_id, "LOCATION", site_str, "site")
            mentions.append(
                Mention(
                    mention_id=loc_m_id,
                    case_id=case_id,
                    doc_id=doc_id,
                    type=EntityType.LOCATION,
                    surface_text=site_str,
                    normalized_value=site_str,
                    origin=Origin.TABLE_PARSER,
                    identifier_trust=IdentifierTrust.STRONG,
                    source=source_ref,
                )
            )

        # Parse Event Time
        date_dict = parse_date_with_profile(timestamp_raw, profile_format=date_format, timezone=tz)
        event_time = EventTime(
            original_text=date_dict["original_text"],
            normalized_iso=date_dict["normalized_iso"],
            timezone=date_dict["timezone"],
            ambiguity=date_dict["ambiguity"],
            notes=date_dict["notes"],
        )

        # Sighting Event
        eid_str = str(event_id_raw) if event_id_raw else f"ANPR-{row_num}"
        sighting_id = make_event_id(doc_id, unit_id, EventType.SIGHTING.value, eid_str, 0)
        events.append(
            Event(
                event_id=sighting_id,
                case_id=case_id,
                type=EventType.SIGHTING,
                description=f"Vehicle {plate_str} sighted by camera {camera_id or ''} at {site or ''}".strip(),
                time=event_time,
                participants=[EventParticipant(mention_id=v_m_id, role="sighted_vehicle")],
                location_mention_id=loc_m_id,
                amount=None,
                origin=Origin.TABLE_PARSER,
                review_flags=[],
                source=source_ref,
            )
        )

        # Review item for unresolved / low confidence plates
        if review_items is not None and (
            str(plate_reviewed).strip() == "UNRESOLVED" or (ocr_conf_val is not None and ocr_conf_val < 0.70)
        ):
            rev_id = make_review_id(case_id, ReviewKind.LOW_TRUST_IDENTIFIER.value, v_m_id, "Unresolved plate OCR")
            review_items.append(
                ReviewItem(
                    review_id=rev_id,
                    case_id=case_id,
                    kind=ReviewKind.LOW_TRUST_IDENTIFIER,
                    target_ids=[v_m_id],
                    detail=f"ANPR plate '{plate_str}' is UNRESOLVED or has low OCR confidence and requires operator confirmation.",
                    status=ReviewItemStatus.OPEN,
                )
            )

    return (events, [], mentions)


__all__ = ["parse_anpr"]
