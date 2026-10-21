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
   LLM_MODEL=mock-extraction-model
   ```

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
| `ATLAS_SYNTHETIC_ONLY` | `true` | Refuses live LLM calls if document hash is not in `data/synthetic_manifest.json` |
| `LLM_PROVIDER` | `mock` | LLM client backend: `mock`, `openai`, `gemini` |
| `LLM_MODEL` | `mock-extraction-model` | Target extraction model (e.g. `gpt-4o`) |
| `OPENAI_API_KEY` | *(empty)* | API key for OpenAI (required only when `LLM_PROVIDER=openai`) |
| `GEMINI_API_KEY` | *(empty)* | API key for Google Gemini (required only when `LLM_PROVIDER=gemini`) |
| `OCR_ENGINE` | `tesseract` | Primary OCR engine: `tesseract` (or `paddle` if extra installed) |
| `OCR_LANGS` | `eng` | Target languages for OCR extraction (e.g. `eng+hin`) |
| `TESSERACT_CMD` | `tesseract` | Path to Tesseract executable |
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

# Verify Gate 4 (API, reports, e2e demo)
python scripts/verify.py --gate 4
```

### 4.2 Generate Synthetic Test Dataset
Generate deterministic synthetic documents and ground-truth labels:
```powershell
python -m synth.generate --seed 42 --out data/synth
```

### 4.3 Run Master Demonstration Script
Execute the full multi-case evidence processing and reviewer resolution lifecycle:
```powershell
# Scripted review lifecycle (automated confirm, merge, audit, split)
python scripts/demo.py --scripted-review

# Interactive review mode
python scripts/demo.py
```

### 4.4 View Generated HTML Evidence Reports
Open the standalone interactive HTML reports in your web browser:
```powershell
# Case A report
Start-Process outputs/CASE-A-001/report.html

# Case B report
Start-Process outputs/CASE-B-002/report.html
```
