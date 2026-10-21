"""Tower location observation parser for tabular evidence.

Parses cell tower location observations into Mention and Event objects.
- Extracts PHONE mentions for target numbers.
- Extracts LOCATION mentions for cell IDs and site descriptions.
- Creates SIGHTING/observation events linking phone and cell site.
"""

from __future__ import annotations

from typing import Any

from atlas.contracts.enums import (
    EntityType,
    EventType,
    IdentifierTrust,
    Origin,
    QuoteStatus,
    UnitKind,
)
from atlas.contracts.ids import (
    make_event_id,
    make_mention_id,
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
from atlas.normalize.identifiers import normalize_phone
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.profiles import create_mapping_unconfirmed_review


def parse_tower(
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
    """Parse Tower Location rows into Events, Aggregates (empty), and Mentions."""
    validate_case_id(case_id)

    if profile is None:
        if review_items is not None:
            review_items.append(
                create_mapping_unconfirmed_review(
                    case_id=case_id,
                    doc_id=doc_id,
                    headers=[],
                    detail="No matching Tower profile provided or confirmed.",
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

        obs_id = get_val(row_vals, "observation_id")
        target_number = get_val(row_vals, "target_number")
        cell_id = get_val(row_vals, "cell_global_id")
        site_desc = get_val(row_vals, "site") or get_val(row_vals, "site_description")
        timestamp_raw = get_val(row_vals, "timestamp") or get_val(row_vals, "event_time_ist")

        if not target_number and not cell_id:
            continue

        target_str = str(target_number).strip() if target_number is not None else "UNKNOWN"
        norm_phone, _ = normalize_phone(target_str)

        # Build SourceRef
        unit_id = make_unit_id_row(doc_id, sheet_index, row_num)
        quote = f"observation_id={obs_id}, target={target_str}, cell={cell_id}, site={site_desc}, time={timestamp_raw}"

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

        # Phone Mention
        p_m_id = make_mention_id(doc_id, unit_id, "PHONE", target_str, "target_number")
        mentions.append(
            Mention(
                mention_id=p_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.PHONE,
                surface_text=target_str,
                normalized_value=norm_phone or target_str,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG,
                source=source_ref,
            )
        )

        # Location Mention for Cell Site
        loc_str = str(cell_id or site_desc).strip()
        loc_m_id = make_mention_id(doc_id, unit_id, "LOCATION", loc_str, "cell_site")
        mentions.append(
            Mention(
                mention_id=loc_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.LOCATION,
                surface_text=loc_str,
                normalized_value=loc_str,
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
        obs_str = str(obs_id) if obs_id else f"LOC-{row_num}"
        sighting_id = make_event_id(doc_id, unit_id, EventType.SIGHTING.value, obs_str, 0)
        events.append(
            Event(
                event_id=sighting_id,
                case_id=case_id,
                type=EventType.SIGHTING,
                description=f"Phone {target_str} observed at cell {cell_id or ''} ({site_desc or ''})".strip(),
                time=event_time,
                participants=[EventParticipant(mention_id=p_m_id, role="observed_phone")],
                location_mention_id=loc_m_id,
                amount=None,
                origin=Origin.TABLE_PARSER,
                review_flags=[],
                source=source_ref,
            )
        )

    return (events, [], mentions)


__all__ = ["parse_tower"]
