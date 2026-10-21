# ATLAS Dev 3 — Document-to-JSON Evidence Pipeline

> [!NOTE]
> **Prototype Demonstration:** ATLAS Dev 3 is an investigative intelligence prototype built for the Smart India Hackathon (SIH). It demonstrates multi-format document intake, deterministic tabular parsing, schema-constrained narrative extraction, quote-verified provenance, and suggestion-only cross-case entity resolution with a cryptographic audit trail.

---

## 1. System Overview

ATLAS (Automated Targeted Ledger and Account Structuring) Dev 3 transforms heterogeneous, unstructured case evidence into cryptographically verified, source-backed structured JSON and graph payloads.

```
+---------------------------------------------------------------------------------------+
|                                    EVIDENCE INTAKE                                    |
|   Scanned FIR (PDF) | Digital PDF | CDR Spreadsheets (XLSX) | Bank Statements (CSV)   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                           DUAL-PATH EXTRACTION & PARSING                              |
|   Direct PDF (`pypdfium2`) | Tesseract OCR (Word BBox/Score) | Deterministic Parsers  |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                        SCHEMA-CONSTRAINED FACT EXTRACTION                             |
|       Entities (Person, Phone, Vehicle, Account) | Relationships | Events             |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                         QUOTE-VERIFIED PROVENANCE VERIFIER                            |
|    Verbatim Quote Check | Source Unit/Row/Line/BBox Computed | Hallucination Reject   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                             WITHIN-CASE CONSOLIDATION                                 |
|      Canonicalization | Contradiction Detection | OCR Uncertainty Gating              |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                    SUGGESTION-ONLY CROSS-CASE ENTITY RESOLVER                         |
|     Shared Signals | Heuristic Ranking ("not a probability") | No Auto-Merge          |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                        AUDITED HUMAN REVIEW & HASH CHAIN                              |
|   `CONFIRM_IDENTIFIER` | `APPROVE_MATCH` | `MERGE` | `SPLIT` | Append-Only SHA-256    |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                                    OUTPUT SINK                                        |
|   `result.json` | `events.jsonl` | `report.html` | Graph Payload | `.cypher` Export   |
+---------------------------------------------------------------------------------------+
```

---

## 2. Core Capabilities

1. **Multi-Format Ingest with Integrity Receipts:**
   - Detects MIME types and inspects file boundaries (size limits, image pixel ceilings, PDF page thresholds).
   - Generates SHA-256 intake receipts (`receipt.json`) and stores original bytes immutably in content-addressed storage (`data/originals/{sha256}`).
2. **Dual-Path Text Extraction:**
   - Native digital PDF extraction via `pypdfium2` preserving font layout.
   - High-resolution scanned document OCR via Tesseract with per-word bounding box coordinates and confidence metrics.
3. **Deterministic Tabular Processing (Zero-LLM):**
   - High-throughput parsing for CDR (`cdr_v1`) and bank statements (`bank_v1`) without sending raw financial records to an LLM.
   - Computes communication volume, duration aggregates, transaction balances, and hidden sheet/formula warnings.
4. **Strict Schema Constraints & Anti-Injection Defense:**
   - Pydantic v2 schemas configured with `extra="forbid"` enforce contract compliance.
   - Document text is treated strictly as untrusted data wrapped in nonce-delimited blocks to neutralize prompt injection attempts.
5. **Quote-Verified Provenance:**
   - The model never creates citations. Line, row, page, and bounding box coordinates are computed by code.
   - Any extracted fact lacking verbatim substring verification against its source unit is rejected with an explicit rejection record.
6. **First-Class Uncertainty & OCR Isolation:**
   - Identifiers derived from OCR are assigned `IdentifierTrust.REVIEW_REQUIRED` and barred from autonomous graph linkage until reviewed.
7. **Suggestion-Only Cross-Case Resolver:**
   - Computes heuristic entity match suggestions with shared signals breakdowns (exact phone match, alias corroboration, co-occurrences).
   - Enforces the non-probabilistic ranking rule: `"heuristic ordering, not a probability"`.
   - Never performs autonomous merges; all linkages require authorized human decisions.
8. **Reversible Cryptographic Audit Trail:**
   - Reviewer actions (`CONFIRM_IDENTIFIER`, `APPROVE_MATCH`, `MERGE`, `SPLIT`) form an append-only SHA-256 hash chain verified via `verify_chain()`.
   - Any approved merge is fully reversible via `SPLIT`, restoring original entity clusters.
9. **Interactive Visual HTML Report:**
   - Self-contained, offline-compatible `report.html` featuring side-by-side raw text and extracted fact viewers with quote highlighting, origin badges, OCR word confidence, and candidate suggestion cards.
   - Prominently displays the honesty banner: `SCRIPTED MOCK PROVIDER: not live extraction` when running in mock mode.
10. **Developer Inspection UI:** Auth-free local page (`python -m atlas ui`) that runs one document through the whole pipeline and shows the run state, extracted entities, connections, events, review queue and graph, with a one-click JSON download of the exact payload it renders and links to the run's canonical artifacts.

---

## 3. Project Documentation

- **[Developer Integration Guide](docs/DEVELOPER_INTEGRATION_GUIDE.md):** Practical integration manual for frontend, backend, and graph engineers (inputs, outputs, and pipeline lifecycle).
- **[Model Architecture Guide](docs/MODEL_GUIDE.md):** In-depth guide explaining WHAT, HOW, WHERE, and WHEN the extraction model & pipeline operate.
- **[Master Build Plan](PLAN.md):** Complete architecture, frozen contracts, algorithm specifications, and task cards.
- **[Setup & Installation Guide](docs/SETUP.md):** Setup guide for Windows (PowerShell 5.1/7), Ubuntu Linux, and macOS.
- **[System Limitations](docs/LIMITATIONS.md):** Formal boundaries: English OCR, unmeasured Indic accuracy, tabular PDF constraints, and DPDP Act prerequisites.
- **[Deliverables Checklist](docs/CHECKLIST.md):** SIH milestone tracking matrix mapping modules to test coverage and gate verification.
- **[Evaluation Report](docs/EVALUATION.md):** Measured mock-provider baseline metrics against synthetic ground truth.
- **[QA & Adversarial Report](docs/QA_REPORT.md):** Gate 5 security audit, adversarial test matrix, and acceptance findings.
- **[Architectural Decisions](docs/DECISIONS.md):** Locked design decisions and rationale.
- **[Implementation Review](docs/IMPLEMENTATION_REVIEW.md):** Independent implementation audit, vulnerability assessment, and remediation findings.
- **[Integration Contract](docs/INTEGRATION_CONTRACT.md):** Graph payload schema and REST API specifications for Dev 2 and Dev 4 hand-off.

---

## 4. Quick Start

### 4.1 Prerequisites
- Python 3.11 or 3.12 (Python 3.14 is unsupported)
- Tesseract OCR (see [SETUP.md](docs/SETUP.md))
- PowerShell 5.1 or 7 on Windows; Bash on Linux/macOS

### 4.2 Setup Virtual Environment
```powershell
# Create virtual environment
py -3.11 -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies (no editable install)
uv pip install -r pyproject.toml --extra dev
# or: python -m pip install ".[dev]"
```

### 4.3 Environment Check
```powershell
python scripts/check_env.py
```

### 4.4 Generate Synthetic Dataset
Generate the deterministic synthetic benchmark dataset with fixed random seed:
```powershell
python -m synth.generate --seed 42 --out data/synth
```

### 4.5 Configure the Extraction Model

`mock` is the offline default. Every **live** provider requires an explicit `LLM_MODEL`: model names are never
defaulted in code (there is no built-in fallback), and the provider must also be enabled for the dev UI.

Groq (the configuration used for live demonstrations):

```env
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=<your key>
OPENAI_BASE_URL=https://api.groq.com/openai/v1
LLM_PROVIDERS_ENABLED=groq
```

OpenAI or Gemini: use the same keys with `LLM_PROVIDER=openai` / `gemini`, the matching
`OPENAI_API_KEY` / `GEMINI_API_KEY`, and set `LLM_PROVIDERS_ENABLED` to the same name. Leaving
`LLM_PROVIDERS_ENABLED` empty offers every provider whose credentials are configured.

`LLM_PROVIDERS_ENABLED` is the authoritative allow-list for the developer UI. Rate limiting is
configurable with `LLM_MAX_REQUESTS_PER_MINUTE` (default `30`), `LLM_RATE_WINDOW_S` (`60`) and
`LLM_MIN_INTERVAL_S` (`0`); retries are handled once, in the client, and honour `Retry-After`.
`python -m atlas run --provider` defaults to `LLM_PROVIDER`, so the flag is optional.

### 4.6 Inspect a Document in the Developer UI

```powershell
$env:PYTHONPATH="src"; $env:PYTHONUTF8="1"
python -m atlas ui --port 8000
```

Open <http://127.0.0.1:8000/>, enter a case ID, choose a file (the page explains why an unregistered
file is refused when `ATLAS_SYNTHETIC_ONLY=true`), and press **Extract**. The page shows a live
elapsed-time counter with **Cancel**, the run `state` as a banner, extracted entities, connections,
events, the review queue, and a graph view. **Download JSON** saves the exact payload the page
renders as `atlas_<case_id>_<run_id>.json`, and the run's canonical artifacts
(`result.json`, `review_queue.json`, `receipt.json`, `events.jsonl`, `trace.jsonl`) are downloadable
from the links below it or from `outputs/<case_id>/<run_id>/`.

---

## 5. Master Demonstration Walkthrough

Run the master demonstration script to observe the complete multi-case evidence processing, OCR uncertainty routing, cross-case suggestion matching, and audited reviewer lifecycle:

```powershell
# Execute the master demonstration (scripted review / interactive)
python -m atlas demo --scripted-review

# Interactive demonstration mode
python -m atlas demo
```

### What the Demo Shows:
1. **Mock Honesty Banner:** Displays `SCRIPTED MOCK PROVIDER: not live extraction` prominently.
2. **Case A Processing:** Processes 5 evidence documents (`FIR_A.pdf`, `IO_REPORT_A.pdf`, `CDR_A.xlsx`, `BANK_A.csv`, `SURVEILLANCE_A.txt`).
3. **Uncertainty Flagging:** OCR phone `+919876543210` from `FIR_A` is flagged `review_required` and quarantined from automatic linkage.
4. **Case B Processing:** Processes `FIR_B.pdf` and `CDR_B.xlsx` under strict case boundary isolation.
5. **Cross-Case Resolution:**
   - Candidate match: Vicky(B) ↔ Vikram Singh(A) flagged `needs_review` with shared phone signal and heuristic rank.
   - Hard negative: Vikram Singh(B) flagged `no_match` / `ambiguous` due to conflicting parentage and age.
6. **Scripted Review Workflow:**
   - Reviewer executes `CONFIRM_IDENTIFIER` for Case A OCR phone.
   - Re-running resolver: phone becomes eligible, elevating the match candidate.
   - Reviewer executes `APPROVE_MATCH` / `MERGE`, creating an audited active merge link.
   - Cryptographic hash chain verification: `verify_chain() == True`.
   - Supervisor directive executes `SPLIT`, cleanly reversing the merge and restoring prior entity states.
7. **Artifact Output:** Generates `outputs/demo_summary.json` and standalone visual reports `outputs/CASE-A-001/report.html` and `outputs/CASE-B-002/report.html`.

---

## 6. CLI Usage

All CLI commands are executed via `python -m atlas` with `PYTHONPATH=src`:

```powershell
# Run evidence pipeline on case files (--provider defaults to LLM_PROVIDER)
python -m atlas run --case CASE-A-001 --files data/synth/FIR_A.pdf data/synth/CDR_A.xlsx

# Force the offline scripted provider for a reproducible run
python -m atlas run --case CASE-A-001 --files data/synth/FIR_A.pdf --provider mock

# Query run status for a case
python -m atlas status --case CASE-A-001 --out outputs

# Output validated CaseResult JSON to stdout
python -m atlas results --case CASE-A-001 --out outputs

# Start the developer inspection UI
python -m atlas ui --port 8000

# Attest an uploaded test file as synthetic (required before a live provider may read it)
python -m atlas register-synthetic data/synth/SURVEILLANCE_A.txt
```

---

## 7. Gate Verification

`scripts/verify.py` runs ruff, mypy and the gate-marked tests with `PYTHONPATH=<worktree>\src` and
`PYTHONUTF8=1`, asserts `atlas.__file__` resolves inside the current worktree, and writes evidence to
`outputs/gates/gate_N.json` (commit hash, clean-tree flag, test counts, skipped tests):

```powershell
# Gate 0: Scaffolding, contracts, configuration
python scripts/verify.py --gate 0

# Gate 1: Ingestion, OCR extraction, tabular parsing
python scripts/verify.py --gate 1

# Gate 2: LLM adapters, prompt formatting, provenance verification
python scripts/verify.py --gate 2

# Gate 3: Pipeline runner, consolidation, suggestion resolver, audit log
python scripts/verify.py --gate 3

# Gate 4: API, graph export, visual reports, developer UI
python scripts/verify.py --gate 4

# Gate 5: Independent QA sign-off
python scripts/verify.py --gate 5

# Cumulative evidence for every gate up to N (used for merge decisions)
python scripts/verify.py --gate 4 --cumulative
```

Tests marked `optional` (Paddle OCR, Indic fixtures) are deselected by default and listed under
`not_run_optional` — never silently skipped. A gate only passes with zero failures, zero errors and
zero skipped tests on this machine.

---

## 8. Standards and Constraints

- **Python Version:** 3.11 / 3.12 only (never 3.14).
- **Encoding:** UTF-8 everywhere (`PYTHONUTF8=1`, `encoding="utf-8"`, `ensure_ascii=False`).
- **Data Privacy:** Synthetic data only (`ATLAS_SYNTHETIC_ONLY=true`). No real PII.
- **Pydantic:** Version 2 with `extra="forbid"`.
- **Determinism:** Sorted JSON keys, fixed seeds, reproducible outputs.
- **PowerShell 5.1:** Use `;` to chain commands (never `&&`).
