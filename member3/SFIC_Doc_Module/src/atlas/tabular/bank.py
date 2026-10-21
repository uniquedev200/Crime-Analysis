"""Bank transaction parser for tabular evidence.

Implements PLAN.md section 5.7:
- Parses bank transaction records into Event, Aggregate, and Mention objects.
- One Event per row with origin=table_parser, assertion=structured_record.
- One Aggregate per (from_account, to_account) pair with count, total_amount, first/last timestamp, and <= 20 sample SourceRefs.
- Extracted fields: txn_id, txn_date, from_account, to_account, amount, currency, narration, balance.
"""

from __future__ import annotations

import re
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
    EventAmount,
    EventParticipant,
    EventTime,
    Mention,
    ReviewItem,
    SourceRef,
)
from atlas.tabular.dates import parse_date_with_profile
from atlas.tabular.profiles import create_mapping_unconfirmed_review, normalize_header


def parse_amount(val: Any) -> tuple[float | None, str | None]:
    """Parse monetary amount string/number, stripping currency symbols and commas."""
    if val is None:
        return None, None

    if isinstance(val, (int, float)):
        return float(val), None

    s = str(val).strip()
    if not s:
        return None, None

    currency: str | None = None
    s_upper = s.upper()
    if "₹" in s or "INR" in s_upper or "RS" in s_upper:
        currency = "INR"
    elif "$" in s or "USD" in s_upper:
        currency = "USD"
    elif "EUR" in s_upper or "€" in s:
        currency = "EUR"

    # Remove currency text, spaces, and commas
    cleaned = re.sub(r"[^\d\.\-+]", "", s)
    try:
        amount_float = float(cleaned)
        return amount_float, currency
    except ValueError:
        return None, currency


def parse_bank(
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
    """Parse bank transaction rows into Events, Aggregates, and Mentions according to profile.

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
                    detail="No matching Bank profile provided or confirmed.",
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

    # Map to track pairs for aggregation: (from_acc, to_acc) -> list of record info
    pair_events: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for idx, row in enumerate(rows, start=2):
        row_num = row.get("row_num", idx)
        if row.get("is_blank", False):
            continue

        row_vals: dict[str, Any] = row.get("values", row)

        txn_id_raw = get_val(row_vals, "txn_id")
        from_acc_raw = get_val(row_vals, "from_account")
        to_acc_raw = get_val(row_vals, "to_account")
        amount_raw = get_val(row_vals, "amount")
        if amount_raw is None:
            debit_val = get_val(row_vals, "debit")
            credit_val = get_val(row_vals, "credit")
            deb_f, _ = parse_amount(debit_val)
            cred_f, _ = parse_amount(credit_val)
            if cred_f is not None and cred_f > 0:
                amount_raw = cred_f
            elif deb_f is not None and deb_f > 0:
                amount_raw = deb_f

        # Skip rows missing essential transaction fields
        if from_acc_raw is None and to_acc_raw is None and amount_raw is None:
            continue

        txn_id = str(txn_id_raw).strip() if txn_id_raw is not None else f"TXN-{row_num}"
        from_acc = str(from_acc_raw).strip() if from_acc_raw is not None else "UNKNOWN"
        to_acc = str(to_acc_raw).strip() if to_acc_raw is not None else "UNKNOWN"

        txn_date_raw = get_val(row_vals, "txn_date")
        currency_raw = get_val(row_vals, "currency")
        narration_raw = get_val(row_vals, "narration")

        narration = str(narration_raw).strip() if narration_raw is not None else None

        # Amount parsing
        amount_float, detected_curr = parse_amount(amount_raw)
        currency = str(currency_raw).strip() if currency_raw is not None else detected_curr

        # Date parsing
        date_dict = parse_date_with_profile(txn_date_raw, profile_format=date_format, timezone=tz)
        event_time = EventTime(
            original_text=date_dict["original_text"],
            normalized_iso=date_dict["normalized_iso"],
            timezone=date_dict["timezone"],
            ambiguity=date_dict["ambiguity"],
            notes=date_dict["notes"],
        )

        unit_id = make_unit_id_row(doc_id, sheet_index, row_num)
        quote = (
            f"txn_id={txn_id}, txn_date={txn_date_raw}, from_account={from_acc}, "
            f"to_account={to_acc}, amount={amount_raw}"
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

        # Mentions for from_account and to_account (skip UNKNOWN)
        if from_acc_raw is not None and from_acc != "UNKNOWN":
            from_m_id = make_mention_id(doc_id, unit_id, "ACCOUNT", from_acc, "from_account")
            from_mention = Mention(
                mention_id=from_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.ACCOUNT,
                surface_text=from_acc,
                normalized_value=from_acc,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG,
                source=source_ref,
            )
            mentions.append(from_mention)

        if to_acc_raw is not None and to_acc != "UNKNOWN":
            to_m_id = make_mention_id(doc_id, unit_id, "ACCOUNT", to_acc, "to_account")
            to_mention = Mention(
                mention_id=to_m_id,
                case_id=case_id,
                doc_id=doc_id,
                type=EntityType.ACCOUNT,
                surface_text=to_acc,
                normalized_value=to_acc,
                origin=Origin.TABLE_PARSER,
                identifier_trust=IdentifierTrust.STRONG,
                source=source_ref,
            )
            mentions.append(to_mention)

        # Create Event
        description = (
            narration
            if narration
            else f"Transfer from {from_acc} to {to_acc} ({amount_raw or ''} {currency or ''})".strip()
        )
        event_id = make_event_id(doc_id, unit_id, EventType.TRANSACTION.value, txn_id, 0)
        event = Event(
            event_id=event_id,
            case_id=case_id,
            type=EventType.TRANSACTION,
            description=description,
            time=event_time,
            participants=[
                EventParticipant(mention_id=from_m_id, role="from_account"),
                EventParticipant(mention_id=to_m_id, role="to_account"),
            ],
            location_mention_id=None,
            amount=EventAmount(
                value_text=str(amount_raw) if amount_raw is not None else "",
                decimal=amount_float,
                currency=currency,
            ),
            origin=Origin.TABLE_PARSER,
            review_flags=[],
            source=source_ref,
        )
        events.append(event)

        # Group for aggregate
        pair_key = (from_acc, to_acc)
        if pair_key not in pair_events:
            pair_events[pair_key] = []
        pair_events[pair_key].append(
            {
                "event": event,
                "source": source_ref,
                "amount": amount_float,
                "iso_ts": date_dict["normalized_iso"],
                "row_num": row_num,
                "from_mention_id": from_m_id,
                "to_mention_id": to_m_id,
            }
        )

    # Build Aggregates
    aggregates: list[Aggregate] = []
    for (_from_a, _to_a), items in pair_events.items():
        sample_sources = [item["source"] for item in items[:20]]
        amounts = [item["amount"] for item in items if item["amount"] is not None]
        total_amount = sum(amounts) if amounts else None

        valid_ts = [item["iso_ts"] for item in items if item["iso_ts"] is not None]
        first_ts = min(valid_ts) if valid_ts else None
        last_ts = max(valid_ts) if valid_ts else None

        row_nums = [item["row_num"] for item in items]
        row_range = [min(row_nums), max(row_nums)]

        first_item = items[0]
        agg_id = make_aggregate_id(
            case_id=case_id,
            type_str=RelType.TRANSFERRED_TO.value,
            subject_mention_id=first_item["from_mention_id"],
            object_mention_id=first_item["to_mention_id"],
        )

        agg = Aggregate(
            aggregate_id=agg_id,
            case_id=case_id,
            type=RelType.TRANSFERRED_TO,
            subject_mention_id=first_item["from_mention_id"],
            object_mention_id=first_item["to_mention_id"],
            count=len(items),
            total_duration_s=None,
            total_amount=total_amount,
            first_ts=first_ts,
            last_ts=last_ts,
            sample_sources=sample_sources,
            events_file=fname,
            events_row_range=row_range,
        )
        aggregates.append(agg)

    return (events, aggregates, mentions)


__all__ = ["parse_amount", "parse_bank"]
