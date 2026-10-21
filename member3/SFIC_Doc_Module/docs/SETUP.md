# ATLAS Dev 3 — Environment Setup and Deployment Guide

This guide details environment setup, dependency management, external tool installation, and verification procedures across Windows (PowerShell 5.1 and PowerShell 7), Linux (Ubuntu/Debian), and macOS.

---

## 1. Prerequisites

- **Python Version:** Python **3.11** or **3.12** is strictly required. Python 3.14 is unsupported.
- **Git:** Git 2.30+ installed. On Windows, ensure long path support is enabled:
  ```powershell
  git config --system core.longpaths true
  ```
- **Tesseract OCR:** Required for scanned PDF and image evidence extraction.
- **Package Manager:** `uv` is recommended for high-speed deterministic dependency management. Alternatively, standard `pip` can be used.

> [!IMPORTANT]
> **No Editable Installs:** ATLAS must never be installed in editable mode (`pip install -e .` is strictly forbidden per AGENTS.md rule 24). Execution occurs via `python -m atlas` with `PYTHONPATH=src` and `PYTHONUTF8=1`.

---

## 2. Platform Installation Guides

### 2.1 Windows (PowerShell 5.1 & PowerShell 7)

1. **Clone or Navigate to the Workspace:**
   ```powershell
   cd SFIC_Doc_Module
   ```

2. **Create and Activate Virtual Environment:**
   ```powershell
   # Create virtual environment with Python 3.11 or 3.12
   py -3.11 -m venv .venv

   # Activate in PowerShell
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install Dependencies (No Editable Install):**
   ```powershell
   # Using uv (preferred):
   uv pip install -r pyproject.toml --extra dev

   # Or using pip:
   python -m pip install --upgrade pip
   python -m pip install ".[dev]"
   ```

4. **Install Tesseract OCR on Windows:**
   - **Using winget:**
     ```powershell
     winget install UB-Mannheim.TesseractOCR
     ```
   - **Manual Installer:** Download the 64-bit installer from the [UB-Mannheim Tesseract Wiki](https://github.com/UB-Mannheim/tesseract/wiki).
   - Install to standard path: `C:\Program Files\Tesseract-OCR\tesseract.exe`.
   - Install language packs for English (`eng`), Hindi (`hin`), and Tamil (`tam`).

5. **Configure Environment Variables:**
   ```powershell
   Copy-Item .env.example .env
   ```
   Ensure `.env` contains:
   ```env
   ATLAS_SYNTHETIC_ONLY=true
   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
   TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
   OCR_ENGINE=tesseract
   OCR_LANGS=eng
   LLM_PROVIDER=mock
   LLM_MODEL=
   ```
   `mock` is the offline default and needs no credentials. For a **live** provider, `LLM_MODEL` is
   mandatory (no model name is defaulted in code). Groq example:
   ```env
   LLM_PROVIDER=groq
   LLM_MODEL=openai/gpt-oss-120b
   GROQ_API_KEY=<your key>
   OPENAI_BASE_URL=https://api.groq.com/openai/v1
   LLM_PROVIDERS_ENABLED=groq
   ```
   Use `LLM_PROVIDER=openai` + `OPENAI_API_KEY`, or `LLM_PROVIDER=gemini` + `GEMINI_API_KEY`, for the
   other adapters. `LLM_PROVIDERS_ENABLED` (comma-separated) is the allow-list for the developer UI;
   leave it empty to offer every provider whose credentials are present.

6. **Run Diagnostics:**
   ```powershell
   python scripts/check_env.py
   ```

---

### 2.2 Linux (Ubuntu 22.04+ / Debian 12+)

1. **Install System Dependencies & Tesseract:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3.11 python3.11-venv python3-pip \
       tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-tam \
       libgl1 libglib2.0-0
   ```

2. **Create and Activate Virtual Environment:**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   python -m pip install --upgrade pip
   python -m pip install ".[dev]"
   ```

4. **Configure Environment:**
   ```bash
   cp .env.example .env
   python scripts/check_env.py
   ```

---

### 2.3 macOS (Apple Silicon / Intel)

1. **Install Prerequisites via Homebrew:**
   ```bash
   brew install python@3.11 tesseract tesseract-lang
   ```

2. **Create and Activate Virtual Environment:**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   python -m pip install --upgrade pip
   python -m pip install ".[dev]"
   ```

4. **Configure Environment:**
   ```bash
   cp .env.example .env
   python scripts/check_env.py
   ```

---

## 3. Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `ATLAS_SYNTHETIC_ONLY` | `true` | Refuses live LLM calls if the document's SHA-256 is not in `data/synthetic_manifest.json` |
| `LLM_PROVIDER` | `mock` | LLM backend: `mock` (offline scripted), `groq`, `openai`, `gemini` |
| `LLM_MODEL` | *(empty)* | Model id. **Required for every live provider**; never defaulted in code (e.g. `openai/gpt-oss-120b`) |
| `LLM_PROVIDERS_ENABLED` | *(empty)* | Comma-separated allow-list for `python -m atlas ui` and `POST /ui/run`; empty offers every provider with credentials |
| `GROQ_API_KEY` | *(empty)* | API key for Groq (required when `LLM_PROVIDER=groq`) |
| `OPENAI_API_KEY` | *(empty)* | API key for OpenAI (required when `LLM_PROVIDER=openai`) |
| `GEMINI_API_KEY` | *(empty)* | API key for Google Gemini (required when `LLM_PROVIDER=gemini`) |
| `OPENAI_BASE_URL` | *(provider SDK default)* | Override the OpenAI-compatible endpoint (e.g. `https://api.groq.com/openai/v1`) |
| `LLM_TEMPERATURE` | `0` | Sampling temperature |
| `LLM_TIMEOUT_S` | `60` | Per-request timeout in seconds |
| `LLM_MAX_ATTEMPTS` | `3` | Retry attempts inside the client (the only retry layer) |
| `LLM_MAX_REQUESTS_PER_MINUTE` | `30` | Client-side pacing ceiling |
| `LLM_RATE_WINDOW_S` | `60.0` | Pacing window in seconds |
| `LLM_MIN_INTERVAL_S` | `0.0` | Minimum spacing between requests |
| `LLM_CHUNK_CHARS` | `12000` | Maximum characters rendered into one prompt chunk |
| `MAX_LLM_CALLS_PER_RUN` | `40` | Hard cap on model calls per run |
| `ENTITY_FILTER_CONFIG` | *(packaged default)* | Path to an alternative `entity_filters.yaml` (person-name lexicons) |
| `OCR_ENGINE` | `tesseract` | Primary OCR engine: `tesseract` (or `paddle` if extra installed) |
| `OCR_LANGS` | `eng` | Target languages for OCR extraction (e.g. `eng+hin`) |
| `TESSERACT_CMD` | `tesseract` | Path to Tesseract executable |
| `ATLAS_REQUIRE_TESSERACT` | `true` | Fail rather than skip when the Tesseract binary is missing |
| `DATA_DIR` | `./data` | Base directory for originals and synthetic benchmarks |
| `OUTPUT_DIR` | `./outputs` | Base directory for pipeline execution outputs |

---

## 4. Verification & Demonstration Commands

### 4.1 Gate Verification Script
Run the automated verification suite to validate code formatting, linting, type safety, and test suites:
```powershell
# Verify Gate 0 (Scaffold, contracts, config)
python scripts/verify.py --gate 0

# Verify Gate 1 (Ingest, OCR, tabular parsers)
python scripts/verify.py --gate 1

# Verify Gate 2 (LLM adapters, provenance verifier)
python scripts/verify.py --gate 2

# Verify Gate 3 (Pipeline runner, entity store, resolver)
python scripts/verify.py --gate 3

# Verify Gate 4 (API, graph export, developer UI, reports)
python scripts/verify.py --gate 4

# Verify Gate 5 (Independent QA sign-off)
python scripts/verify.py --gate 5

# Cumulative evidence for gates 0..N (used for merge decisions)
python scripts/verify.py --gate 4 --cumulative
```

`verify.py` writes `outputs/gates/gate_N.json` with the commit hash, clean-tree flag, test counts and
the names of any skipped tests. A gate passes only with zero failures, errors and skips; the
`optional` tests (Paddle OCR, Indic fixtures) are deselected rather than skipped.

### 4.2 Generate Synthetic Test Dataset
Generate deterministic synthetic documents and ground-truth labels:
```powershell
python -m synth.generate --seed 42 --out data/synth
```

### 4.3 Run Master Demonstration Script
Execute the full multi-case evidence processing and reviewer resolution lifecycle:
```powershell
# Scripted review lifecycle (automated confirm, merge, audit, split)
python -m atlas demo --scripted-review

# Interactive review mode
python -m atlas demo
```

### 4.4 Inspect a Document in the Developer UI
Run one document through the pipeline and inspect entities, connections and events in the browser:
```powershell
python -m atlas ui --port 8000
```
Open <http://127.0.0.1:8000/>, enter a case ID, choose a synthetic file and press **Extract**. The page
offers only the providers in `LLM_PROVIDERS_ENABLED`, explains a `ATLAS_SYNTHETIC_ONLY` refusal
instead of returning an empty result, shows a live elapsed-time counter with **Cancel**, and can
download the run payload as JSON (`Download JSON`) or the canonical artifacts from
`outputs/<case_id>/<run_id>/`.

### 4.5 View Generated HTML Evidence Reports
Open the standalone interactive HTML reports in your web browser:
```powershell
# Case A report
Start-Process outputs/CASE-A-001/report.html

# Case B report
Start-Process outputs/CASE-B-002/report.html
```
