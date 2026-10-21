"""Gate 1 unit tests for CSV tabular reader and CDR/Bank parsers.

Marked with @pytest.mark.gate1.
Tests deterministic reading, delimiter sniffing, ragged rows, leading zeros,
15-digit IMEIs, encoding fallback, blank rows, and event/aggregate generation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas.contracts.enums import EntityType, EventType, IdentifierTrust, Origin, RelType
from atlas.contracts.ids import make_doc_id, make_unit_id_row
from atlas.tabular.bank import parse_bank
from atlas.tabular.cdr import parse_cdr
from atlas.tabular.csv_reader import read_csv, sniff_delimiter


@pytest.mark.gate1
def test_csv_quoted_delimiters(tmp_path: Path) -> None:
    csv_file = tmp_path / "quoted.csv"
    csv_file.write_text(
        "a_party,b_party,start_time,duration_s,call_type,narration\n"
        '9876543210,9123456780,2023-01-01 10:00:00,120,VOICE,"Call regarding case, incident report; details follow"\n',
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    assert result["delimiter"] == ","
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["narration"] == "Call regarding case, incident report; details follow"


@pytest.mark.gate1
def test_csv_empty_values(tmp_path: Path) -> None:
    csv_file = tmp_path / "empty_vals.csv"
    csv_file.write_text(
        'col1,col2,col3,col4\nval1,,"",val4\n',
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["col1"] == "val1"
    assert row["col2"] == ""
    assert row["col3"] == ""
    assert row["col4"] == "val4"


@pytest.mark.gate1
def test_csv_leading_zero_ids(tmp_path: Path) -> None:
    csv_file = tmp_path / "leading_zeros.csv"
    csv_file.write_text(
        "phone,account_id\n09876543210,00123456789\n",
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    row = result["rows"][0]
    assert row["phone"] == "09876543210"
    assert row["account_id"] == "00123456789"
    assert isinstance(row["phone"], str)
    assert isinstance(row["account_id"], str)


@pytest.mark.gate1
def test_csv_15_digit_imei_never_float(tmp_path: Path) -> None:
    csv_file = tmp_path / "imei.csv"
    csv_file.write_text(
        "imei,sim_id\n860123456789012,8991234567890123456\n",
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    row = result["rows"][0]
    assert row["imei"] == "860123456789012"
    assert "e" not in row["imei"].lower()
    assert "." not in row["imei"]
    assert isinstance(row["imei"], str)


@pytest.mark.gate1
def test_csv_ragged_rows_warn(tmp_path: Path) -> None:
    csv_file = tmp_path / "ragged.csv"
    csv_file.write_text(
        "h1,h2,h3\na,b,c\nshort_val\nd,e,f,extra1,extra2\ng,h,i\n",
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    # Rows should never be dropped
    assert len(result["rows"]) == 4
    # Warnings should include physical row numbers (counting header as row 1)
    # short_val is row 3, extra line is row 4
    warnings = result["warnings"]
    assert any("row 3" in w for w in warnings)
    assert any("row 4" in w for w in warnings)
    assert result["rows"][1]["row_num"] == 3
    assert result["rows"][2]["row_num"] == 4


@pytest.mark.gate1
def test_csv_blank_rows_preserved(tmp_path: Path) -> None:
    csv_file = tmp_path / "blanks.csv"
    csv_file.write_text(
        "c1,c2\nv1,v2\n\n   ,   \nv3,v4\n",
        encoding="utf-8",
    )
    result = read_csv(csv_file)
    assert len(result["rows"]) == 4
    assert result["rows"][0]["is_blank"] is False
    assert result["rows"][1]["is_blank"] is True
    assert result["rows"][2]["is_blank"] is True
    assert result["rows"][3]["is_blank"] is False


@pytest.mark.gate1
def test_csv_delimiter_sniffing(tmp_path: Path) -> None:
    # Test semicolon
    f_semi = tmp_path / "semi.csv"
    f_semi.write_text("a;b;c\n1;2;3\n4;5;6\n", encoding="utf-8")
    assert sniff_delimiter(f_semi.read_text(encoding="utf-8")) == ";"

    # Test tab
    f_tab = tmp_path / "tab.csv"
    f_tab.write_text("a\tb\tc\n1\t2\t3\n4\t5\t6\n", encoding="utf-8")
    assert sniff_delimiter(f_tab.read_text(encoding="utf-8")) == "\t"

    # Test pipe
    f_pipe = tmp_path / "pipe.csv"
    f_pipe.write_text("a|b|c\n1|2|3\n4|5|6\n", encoding="utf-8")
    assert sniff_delimiter(f_pipe.read_text(encoding="utf-8")) == "|"


@pytest.mark.gate1
def test_csv_latin1_fallback(tmp_path: Path) -> None:
    csv_file = tmp_path / "latin1.csv"
    # Write Latin-1 bytes with accent not valid in UTF-8
    content_bytes = "name,amount\nCafé,100\n".encode("latin-1")
    csv_file.write_bytes(content_bytes)

    result = read_csv(csv_file, encoding="utf-8-sig")
    assert any("latin-1" in w for w in result["warnings"])
    assert len(result["rows"]) == 1
    assert result["rows"][0]["name"] == "Café"


@pytest.mark.gate1
def test_csv_stable_row_ids(tmp_path: Path) -> None:
    csv_file = tmp_path / "stable.csv"
    csv_file.write_text(
        "id,val\n1,a\n2,b\n3,c\n",
        encoding="utf-8",
    )
    parse1 = read_csv(csv_file)
    parse2 = read_csv(csv_file)

    doc_id = make_doc_id("a" * 64)
    unit_ids_1 = [make_unit_id_row(doc_id, 0, r["row_num"]) for r in parse1["rows"]]
    unit_ids_2 = [make_unit_id_row(doc_id, 0, r["row_num"]) for r in parse2["rows"]]

    assert unit_ids_1 == unit_ids_2
    assert unit_ids_1 == [f"{doc_id}:s00:r000002", f"{doc_id}:s00:r000003", f"{doc_id}:s00:r000004"]


@pytest.mark.gate1
def test_csv_cdr_parsing_and_aggregates(tmp_path: Path) -> None:
    csv_file = tmp_path / "cdr.csv"
    csv_file.write_text(
        "a_party,b_party,start_time,duration_s,call_type,imei,cell_id\n"
        "9876543210,9123456780,2023-01-01 10:00:00,60,VOICE,860123456789012,CELL-001\n"
        "9876543210,9123456780,2023-01-01 11:00:00,120,VOICE,860123456789012,CELL-001\n"
        "9123456780,9876543210,2023-01-01 12:00:00,45,VOICE,860987654321098,CELL-002\n"
        "\n",
        encoding="utf-8",
    )
    csv_data = read_csv(csv_file)
    profile = {
        "name": "cdr_v1",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "timezone": "Asia/Kolkata",
    }
    case_id = "CASE_2026_001"
    doc_id = make_doc_id("b" * 64)

    events, aggregates, mentions = parse_cdr(csv_data["rows"], profile, case_id, doc_id)

    # 3 non-blank data rows -> 3 events
    assert len(events) == 3
    # Check invariant: aggregate counts equal event row count
    total_aggregate_count = sum(agg.count for agg in aggregates)
    assert total_aggregate_count == len(events)

    # Check pair aggregation: 2 pairs: (9876543210, 9123456780) and (9123456780, 9876543210)
    assert len(aggregates) == 2
    agg_map = {(agg.subject_mention_id, agg.object_mention_id): agg for agg in aggregates}
    assert len(agg_map) == 2
    # One pair has count 2, one has count 1
    counts = sorted(agg.count for agg in aggregates)
    assert counts == [1, 2]

    # Verify event properties
    for ev in events:
        assert ev.type == EventType.CALL
        assert ev.origin == Origin.TABLE_PARSER
        assert ev.case_id == case_id
        assert ev.source.quote_status.value == "verified"

    # Verify mentions
    phone_mentions = [m for m in mentions if m.type == EntityType.PHONE]
    assert len(phone_mentions) == 6  # 2 per call
    for pm in phone_mentions:
        assert pm.identifier_trust == IdentifierTrust.STRONG
        assert pm.origin == Origin.TABLE_PARSER


@pytest.mark.gate1
def test_csv_bank_parsing_and_aggregates(tmp_path: Path) -> None:
    csv_file = tmp_path / "bank.csv"
    csv_file.write_text(
        "txn_id,txn_date,from_account,to_account,amount,currency,narration\n"
        'TXN001,01/01/2023,ACC1001,ACC2002,"1,50,000.00",INR,Consulting fee\n'
        'TXN002,02/01/2023,ACC1001,ACC2002,"50,000.00",INR,Advance payment\n'
        'TXN003,03/01/2023,ACC3003,ACC1001,"25,000.00",INR,Refund\n',
        encoding="utf-8",
    )
    csv_data = read_csv(csv_file)
    profile = {
        "name": "bank_v1",
        "date_format": "%d/%m/%Y",
        "timezone": "Asia/Kolkata",
    }
    case_id = "CASE_BANK_001"
    doc_id = make_doc_id("c" * 64)

    events, aggregates, _mentions = parse_bank(csv_data["rows"], profile, case_id, doc_id)

    assert len(events) == 3
    # Invariant: Aggregate count equals number of transaction events
    assert sum(agg.count for agg in aggregates) == len(events)

    # Verify amounts
    assert events[0].amount is not None
    assert events[0].amount.decimal == 150000.0
    assert events[0].amount.currency == "INR"

    # Aggregates: ACC1001->ACC2002 has total 200000.0
    agg_1 = next(agg for agg in aggregates if agg.count == 2)
    assert agg_1.type == RelType.TRANSFERRED_TO
    assert agg_1.total_amount == 200000.0


@pytest.mark.gate1
def test_csv_cdr_scale_parsing(tmp_path: Path) -> None:
    csv_file = tmp_path / "cdr_scale.csv"
    lines = ["a_party,b_party,start_time,duration_s,call_type\n"]
    for i in range(1000):
        lines.append(f"9876543210,912345678{i % 10},2023-01-01 10:00:00,60,VOICE\n")
    csv_file.write_text("".join(lines), encoding="utf-8")

    csv_data = read_csv(csv_file)
    profile = {
        "name": "cdr_v1",
        "date_format": "%Y-%m-%d %H:%M:%S",
        "timezone": "Asia/Kolkata",
    }
    case_id = "CASE_SCALE_001"
    doc_id = make_doc_id("f" * 64)

    events, aggregates, _mentions = parse_cdr(csv_data["rows"], profile, case_id, doc_id)
    assert len(events) == 1000
    assert sum(agg.count for agg in aggregates) == 1000
    assert len(aggregates) == 10
