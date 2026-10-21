"""CDR (Call Detail Record) parser for tabular data.

Implements PLAN.md section 5.7:
- Parses CDR records into Event, Aggregate, and Mention objects.
- One Event per row with origin=table_parser, assertion=structured_record.
- One Aggregate per (A, B) pair with count, duration, first/last timestamp, and <= 20 sample SourceRefs.
- Extracted fields: a_party, b_party, start_time, duration_s, call_type, imei, cell_id.
"""

from __future__ import annotations

from typing import Any

from atlas.contracts.enums import (
    EntityType,
    EventType,
    IdentifierTrust,
    Origin,
    QuoteStatus,
    RelType,
    UnitKind,
)
from atlas.contracts.ids import (
    make_aggregate_id,
    make_event_id,
    make_mention_id,
    make_unit_id_row,
    validate_case_id,
)
from atlas.contracts.records import (
    Aggregate,
    Event,
    EventParticipant,
    EventTime,
    Mention,
    ReviewItem,
    SourceRef,
)
from atlas.normalize.identifiers import normalize_phone, validate_imei
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.profiles import create_mapping_unconfirmed_review, normalize_header


def parse_cdr(
    rows: list[dict[str, Any]],
    profile: dict[str, Any] | None,
    case_id: str,
    doc_id: str,
    file_name: str | None = None,
    file_sha256: str | None = None,
    sheet_index: int = 0,
    sheet_name: str | None = None,
    review_items: list[ReviewItem] | None = None,
) -> tuple[list[Event], list[Aggregate], list[Mention]]:
    """Parse CDR rows into Events, Aggregates, and Mentions according to profile.

    If profile is None, triggers mapping_unconfirmed and returns zero facts.
    """
    validate_case_id(case_id)

    if profile is None:
        if review_items is not None:
            review_items.append(
                create_mapping_unconfirmed_review(
                    case_id=case_id,
                    doc_id=doc_id,
                    headers=[],
                    detail="No matching CDR profile provided or confirmed.",
                )
            )
        return ([], [], [])

    fname = file_name or f"{doc_id}.csv"
    fsha = file_sha256 or (doc_id[4:].ljust(64, "0") if len(doc_id) > 4 else "0" * 64)

    aliases: dict[str, str] = profile.get("header_aliases", {})
    date_format: str | None = profile.get("date_format")
    tz: str | None = profile.get("timezone")

    norm_aliases = {normalize_header(str(k)): v for k, v in aliases.items()}

    def get_val(row_vals: dict[str, Any], canonical_key: str) -> Any:
        norm_row = {normalize_header(str(k)): v for k, v in row_vals.items()}
        # Check canonical
        if canonical_key in norm_row and norm_row[canonical_key] is not None:
            v = str(norm_row[canonical_key]).strip()
            if v != "":
                return norm_row[canonical_key]
        # Check aliases
        for alias, target in norm_aliases.items():
            if target == canonical_key and alias in norm_row and norm_row[alias] is not None:
                v = str(norm_row[alias]).strip()
                if v != "":
                    return norm_row[alias]
        return None

    events: list[Event] = []
    mentions: list[Mention] = []

    # Map to track pairs for aggregation: (a_party, b_party) -> list[tuple[Event, SourceRef, float, str | None]]
    pair_events: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for idx, row in enumerate(rows, start=2):
        row_num = row.get("row_num", idx)
        if row.get("is_blank", False):
            continue

        row_vals: dict[str, Any] = row.get("values", row)

        a_party_raw = get_val(row_vals, "a_party")
        b_party_raw = get_val(row_vals, "b_party")

        # Skip if missing required party identifiers
        if a_party_raw is None and b_party_raw is None:
            continue

        a_party = str(a_party_raw).strip() if a_party_raw is not None else "UNKNOWN"
        b_party = str(b_party_raw).strip() if b_party_raw is not None else "UNKNOWN"

        start_time_raw = get_val(row_vals, "start_time")
        if start_time_raw is None:
            c_date = get_val(row_vals, "call_date")
            c_time = get_val(row_vals, "call_time")
            if c_date and c_time:
                start_time_raw = f"{c_date} {c_time}"
            elif c_date:
                start_time_raw = str(c_date)

        duration_raw = get_val(row_vals, "duration_s")
        call_type_raw = get_val(row_vals, "call_type")
        imei_raw = get_val(row_vals, "imei")
        cell_id_raw = get_val(row_vals, "cell_id")

        call_type = str(call_type_raw).strip() if call_type_raw is not None else "CALL"
        imei = str(imei_raw).strip() if imei_raw is not None else None
        cell_id = str(cell_id_raw).strip() if cell_id_raw is not None else None

        duration_s: float = 0.0
        if duration_raw is not None:
            try:
                duration_s = float(str(duration_raw).strip())
            except ValueError:
                duration_s = 0.0

        # Parse date
        date_dict = parse_date_with_profile(start_time_raw, profile_format=date_format, timezone=tz)
        event_time = EventTime(
            original_text=date_dict["original_text"],
            normalized_iso=date_dict["normalized_iso"],
            timezone=date_dict["timezone"],
            ambiguity=date_dict["ambiguity"],
            notes=date_dict["notes"],
        )

        # Build SourceRef
        unit_id = make_unit_id_row(doc_id, sheet_index, row_num)
        quote = (
            f"a_party={a_party}, b_party={b_party}, start_time={start_time_raw}, "
            f"duration_s={duration_raw}, call_type={call_type}"
        )

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

        # Mentions for A and B (skip UNKNOWN)
        if a_party_raw is not None and a_party != "UNKNOWN":
            norm_a, _ = normalize_phone(a_party)
            a_m_id = make_mention_id(doc_id, unit_id, "PHONE", a_party, "a_party")
            a_mention = Mention(
                mention_id=a_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.PHONE,
                surface_text=a_party,
                normalized_value=norm_a or a_party,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG if norm_a else IdentifierTrust.REVIEW_REQUIRED,
                source=source_ref,
            )
            mentions.append(a_mention)

        if b_party_raw is not None and b_party != "UNKNOWN":
            norm_b, _ = normalize_phone(b_party)
            b_m_id = make_mention_id(doc_id, unit_id, "PHONE", b_party, "b_party")
            b_mention = Mention(
                mention_id=b_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.PHONE,
                surface_text=b_party,
                normalized_value=norm_b or b_party,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG if norm_b else IdentifierTrust.REVIEW_REQUIRED,
                source=source_ref,
            )
            mentions.append(b_mention)

        # Optional mentions: IMEI, Location (cell_id)
        if imei and imei != "UNKNOWN":
            norm_imei, _ = validate_imei(imei)
            imei_m_id = make_mention_id(doc_id, unit_id, "IMEI", imei, "imei")
            mentions.append(
                Mention(
                    mention_id=imei_m_id,
                    case_id=case_id,
                    doc_id=doc_id,
                    type=EntityType.IMEI,
                    surface_text=imei,
                    normalized_value=norm_imei or imei,
                    origin=Origin.TABLE_PARSER,
                    identifier_trust=IdentifierTrust.STRONG if norm_imei else IdentifierTrust.REVIEW_REQUIRED,
                    source=source_ref,
                )
            )

        loc_m_id: str | None = None
        if cell_id:
            loc_m_id = make_mention_id(doc_id, unit_id, "LOCATION", cell_id, "cell_id")
            mentions.append(
                Mention(
                    mention_id=loc_m_id,
                    case_id=case_id,
                    doc_id=doc_id,
                    type=EntityType.LOCATION,
                    surface_text=cell_id,
                    normalized_value=cell_id,
                    origin=Origin.TABLE_PARSER,
                    identifier_trust=IdentifierTrust.STRONG,
                    source=source_ref,
                )
            )

        # Create Event
        event_id = make_event_id(doc_id, unit_id, EventType.CALL.value, f"{a_party}->{b_party}", 0)
        event = Event(
            event_id=event_id,
            case_id=case_id,
            type=EventType.CALL,
            description=f"Call ({call_type}) from {a_party} to {b_party} ({duration_s}s)",
            time=event_time,
            participants=[
                EventParticipant(mention_id=a_m_id, role="a_party"),
                EventParticipant(mention_id=b_m_id, role="b_party"),
            ],
            location_mention_id=loc_m_id,
            amount=None,
            origin=Origin.TABLE_PARSER,
            review_flags=[],
            source=source_ref,
        )
        events.append(event)

        # Track for aggregation
        pair_key = (a_party, b_party)
        if pair_key not in pair_events:
            pair_events[pair_key] = []
        pair_events[pair_key].append(
            {
                "event": event,
                "source": source_ref,
                "duration_s": duration_s,
                "iso_ts": date_dict["normalized_iso"],
                "row_num": row_num,
                "a_mention_id": a_m_id,
                "b_mention_id": b_m_id,
            }
        )

    # Build Aggregates
    aggregates: list[Aggregate] = []
    for (_a, _b), items in pair_events.items():
        sample_sources = [item["source"] for item in items[:20]]
        total_duration = sum(item["duration_s"] for item in items)

        valid_ts = [item["iso_ts"] for item in items if item["iso_ts"] is not None]
        first_ts = min(valid_ts) if valid_ts else None
        last_ts = max(valid_ts) if valid_ts else None

        row_nums = [item["row_num"] for item in items]
        row_range = [min(row_nums), max(row_nums)]

        first_item = items[0]
        agg_id = make_aggregate_id(
            case_id=case_id,
            type_str=RelType.CALLED.value,
            subject_mention_id=first_item["a_mention_id"],
            object_mention_id=first_item["b_mention_id"],
        )

        agg = Aggregate(
            aggregate_id=agg_id,
            case_id=case_id,
            type=RelType.CALLED,
            subject_mention_id=first_item["a_mention_id"],
            object_mention_id=first_item["b_mention_id"],
            count=len(items),
            total_duration_s=total_duration,
            total_amount=None,
            first_ts=first_ts,
            last_ts=last_ts,
            sample_sources=sample_sources,
            events_file=fname,
            events_row_range=row_range,
        )
        aggregates.append(agg)

    return (events, aggregates, mentions)


__all__ = ["parse_cdr"]
