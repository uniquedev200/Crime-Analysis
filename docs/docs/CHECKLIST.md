# ATLAS Dev 3 — SIH Deliverables and Verification Checklist

This document tracks implementation, module ownership, test coverage, and gate verification status across all Smart India Hackathon (SIH) deliverables per PLAN.md Section 8, 9, and 11.

---

## 1. Core Deliverables Matrix

| # | SIH Deliverable | Scope / Feature | Code Modules | Backed By Tests | Gate | Status |
|---|---|---|---|---|---|---|
| 1 | **Multi-Format Intake & Integrity** | Multi-file intake (PDF, XLSX, CSV, TXT, JSON); SHA-256 intake receipts; immutable content-addressed storage; synthetic data guard. | `src/atlas/ingest/` (`detect.py`, `integrity.py`, `limits.py`, `originals.py`, `synthetic_guard.py`) | `tests/unit/test_ingest_detect.py`<br>`tests/unit/test_ingest_integrity.py`<br>`tests/unit/test_ingest_limits.py` | Gate 1 | **PASSED** |
| 2 | **Dual-Path Text & Scanned OCR** | Direct digital PDF extraction via `pypdfium2`; Tesseract OCR with per-word confidence metrics; Indic language pack plumbing; image deskewing. | `src/atlas/extract/` (`pdf.py`, `image.py`, `text.py`, `jsonfile.py`, `units.py`) | `tests/unit/test_extract_pdf.py`<br>`tests/unit/test_ocr_tesseract.py`<br>`tests/unit/test_ocr_preprocess.py` | Gate 1 | **PASSED** |
| 3 | **Deterministic Tabular Processing** | Zero-LLM parsing for CDR (`cdr_v1`) and Bank statements (`bank_v1`); formula/hidden sheet warnings; transaction & call aggregates computation. | `src/atlas/tabular/` (`cdr.py`, `bank.py`, `xlsx_reader.py`, `csv_reader.py`, `profiles.py`, `dates.py`) | `tests/unit/test_tabular_cdr.py`<br>`tests/unit/test_tabular_bank.py`<br>`tests/unit/test_tabular_xlsx.py`<br>`tests/unit/test_tabular_csv.py` | Gate 1 | **PASSED** |
| 4 | **Identifier Normalization & Trust** | Phone numbers (E.164), IMEIs (Luhn check), Indian vehicle plates, bank account padding; Indian name keying; OCR low-trust flag. | `src/atlas/normalize/` (`identifiers.py`, `names.py`, `dates.py`) | `tests/unit/test_normalize_identifiers.py`<br>`tests/unit/test_normalize_names.py`<br>`tests/unit/test_normalize_dates.py` | Gate 1 | **PASSED** |
| 5 | **Schema-Constrained LLM Extraction** | Pydantic-validated narrative extraction of mentions, relationships, and events; anti-prompt-injection delimiter defense; swappable providers. | `src/atlas/llm/` (`client.py`, `build_prompt.py`, `mock.py`, `retry.py`, `adapters/`) | `tests/unit/test_llm_client.py`<br>`tests/unit/test_llm_build_prompt.py`<br>`tests/unit/test_llm_retry.py`<br>`tests/unit/test_llm_adapters.py` | Gate 2 | **PASSED** |
| 6 | **Quote-Verified Provenance** | Verbatim quote verification against source units; computed line/page/row/bbox coordinates; rejection of unverified model hallucinations. | `src/atlas/provenance/` (`verify.py`, `chunking.py`, `normalize_text.py`, `locate.py`) | `tests/unit/test_provenance_verify.py`<br>`tests/unit/test_provenance_chunking.py` | Gate 2 | **PASSED** |
| 7 | **Within-Document & Case Consolidation** | Entity clustering across document units; contradiction tracking (conflicting roles, dates); unconfirmed OCR isolation. | `src/atlas/consolidate/` (`within_doc.py`, `within_case.py`) | `tests/unit/test_consolidate_within_doc.py`<br>`tests/unit/test_consolidate_contradictions.py` | Gate 3 | **PASSED** |
| 8 | **Case Isolation & Pipeline Runner** | End-to-end multi-file pipeline runner; deterministic run IDs and idempotency keys; strict tenant/case isolation. | `src/atlas/pipeline/` (`runner.py`, `jobs.py`, `status.py`) | `tests/integration/test_pipeline_runner.py`<br>`tests/integration/test_pipeline_isolation.py`<br>`tests/integration/test_pipeline_cli.py` | Gate 3 | **PASSED** |
| 9 | **Suggestion-Only Cross-Case Resolver** | Heuristic entity candidate generation (`needs_review`, `candidate`, `ambiguous`); shared signal breakdown; non-probabilistic ranking. | `src/atlas/resolve/` (`candidates.py`, `signals.py`, `nameutils.py`, `store_sqlite.py`) | `tests/unit/test_resolve_signals.py`<br>`tests/unit/test_resolve_engine.py`<br>`tests/integration/test_resolve_integration.py` | Gate 3 | **PASSED** |
| 10 | **Audited Review Actions & Hash Chain** | Human actions (`CONFIRM_IDENTIFIER`, `APPROVE_MATCH`, `MERGE`, `SPLIT`); append-only SHA-256 hash chain; `verify_chain()` validation. | `src/atlas/resolve/` (`review.py`, `audit.py`) | `tests/unit/test_resolve_audit.py`<br>`tests/integration/test_resolve_integration.py` | Gate 3 | **PASSED** |
| 11 | **Graph Export & Dev 4 Hand-off** | Canonical graph payload (`nodes`, `edges`), Neo4j `.cypher` export, Dev 4 mapping layer; unconfirmed/suggestion isolation. | `src/atlas/output/` (`graph_payload.py`, `cypher_export.py`)<br>`src/atlas/adapters/dev4_graph.py` | `tests/contract/test_adapters_dev4.py` | Gate 4 | In Progress (J4) |
| 12 | **Dev 2 REST API & Job States** | FastAPI service; asynchronous job execution; explicit `JobState` values; token/user auth stub; failure simulation. | `src/atlas/api/` (`app.py`, `routes.py`, `auth.py`)<br>`src/atlas/adapters/dev2_http.py` | `tests/contract/test_api_routes.py`<br>`tests/contract/test_api_auth.py`<br>`tests/contract/test_adapters_dev2.py` | Gate 4 | In Progress (J4) |
| 13 | **Visual HTML Evidence Report** | Standalone self-contained `report.html`; side-by-side viewer; quote highlights; OCR confidence; mock banner; strict XSS autoescaping. | `src/atlas/output/report_html.py`<br>`src/atlas/output/templates/report.html.j2` | `tests/e2e/test_report_html.py` | Gate 4 | **PASSED (K4)** |
| 14 | **Master Demonstration & E2E Acceptance** | Master demo script with automated/scripted review lifecycle (`confirm` -> `rerun` -> `merge` -> `audit` -> `split`); golden summary reproduction. | `scripts/demo.py`<br>`tests/e2e/expected_demo_summary.json` | `tests/e2e/test_demo.py` | Gate 4 | **PASSED (K4)** |
| 15 | **Adversarial & Injection Hardening** | Prompt injection resistance fixtures, oversize/bomb files rejection, corrupt input isolation, concurrency tests. | `tests/adversarial/` | `tests/adversarial/test_*.py` | Gate 5 | Scheduled (Q5) |

---

## 2. Wave 4 (Worker K4) Deliverable Verification Detail

| Deliverable Path | Description | Test File | Gate Mark | Verification Result |
|---|---|---|---|---|
| `src/atlas/output/report_html.py` | Standalone HTML report generator with side-by-side raw text / fact viewer, quote highlights, and case isolation. | `tests/e2e/test_report_html.py` | `@pytest.mark.gate4` | **5 / 5 passed** |
| `src/atlas/output/templates/report.html.j2` | Jinja2 template with embedded CSS/JS, mock honesty banner, OCR badges, suggestion cards, and audit trail table. | `tests/e2e/test_report_html.py` | `@pytest.mark.gate4` | **Verified** |
| `scripts/demo.py` | Master demo script executing Case A, Case B, OCR uncertainty, cross-case matching, and scripted review lifecycle. | `tests/e2e/test_demo.py` | `@pytest.mark.gate4` | **1 / 1 passed (13.85s)** |
| `tests/e2e/expected_demo_summary.json` | Canonical golden summary file recording exact deterministic run metrics and cryptographic audit hashes. | `tests/e2e/test_demo.py` | `@pytest.mark.gate4` | **Byte-for-byte match** |
| `docs/LIMITATIONS.md` | Formal boundary specifications: English OCR, handwriting unmeasured, tabular PDFs flagged, local SQLite stub, DPDP Act. | Docs inspection | N/A | **Complete** |
| `docs/SETUP.md` | Multi-platform setup guide covering Windows (PowerShell 5.1/7), Ubuntu Linux, and macOS with Tesseract OCR install. | Docs inspection | N/A | **Complete** |
| `docs/CHECKLIST.md` | SIH deliverable tracking matrix mapping each module to tests, gates, and acceptance status. | Docs inspection | N/A | **Complete** |
| `README.md` | Comprehensive project overview, architecture diagram, CLI usage, and demo execution walkthrough. | Docs inspection | N/A | **Complete** |

---

## 3. Gate Status Tracking

- [x] **Gate 0:** Contracts, schemas, configuration, logging, and import boundaries (`gate_0.json` written).
- [x] **Gate 1:** Ingest, OCR extraction, tabular parsing, normalization, synthetic generator (`gate_1.json` written).
- [x] **Gate 2:** LLM client adapters, prompt formatting, quote verification, provenance chunking (`gate_2.json` written).
- [x] **Gate 3:** Pipeline execution, within-case consolidation, suggestion resolver, audit trail (`gate_3.json` written).
- [ ] **Gate 4:** Graph export, Dev 2/Dev 4 adapters, REST API, HTML report, master demo (K4 deliverables passed; J4 in progress).
- [ ] **Gate 5:** Adversarial hardening, synthetic benchmark evaluation, clean-clone reproduction.
