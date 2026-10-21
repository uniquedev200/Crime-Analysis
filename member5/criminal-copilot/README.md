# AI-Powered Criminal Investigation Copilot
**Module: Member 5 — AI-Assisted Search and Investigation Reporting**

## Overview
This repository contains the backend and reporting module for the **AI-Powered Criminal Investigation Copilot** college project. The goal of Member 5's module is to help investigators query case records using natural language, retrieve grounded evidence with exact source citations, compute accurate counts and totals in Python, suggest relevant follow-up questions, and generate structured investigation reports.

Designed to run locally on an **Apple Silicon Mac (8 GB unified memory)** using **Python** and a local **Ollama** model (`qwen2.5:3b`), this module operates completely offline without any external hosted LLM APIs.

---

## Core Investigation & Safety Principles
1. **Local-Only AI Inference**: Uses a locally running Ollama instance (`qwen2.5:3b`). No data is sent to external cloud AI services.
2. **Strict Evidence Grounding**: Never invents facts or extrapolates beyond the provided JSON records.
3. **Strict Case Isolation**: Never mixes records, entities, or timelines from different `case_id` contexts.
4. **Objective Reporting**: Never treats an association, contact, or presence in a record as proof of guilt.
5. **Explicit Uncertainty**: Clearly indicates when evidence is missing, incomplete, or insufficient to answer a query.
6. **Deterministic Calculations**: Uses Python (not LLM guesswork) to calculate exact record counts, frequencies, and financial/numeric totals.
7. **Full Source Traceability**: Preserves `record_id`, `document_name`, `page_number`, and `timestamp` whenever available.

---

## Project Folder Structure

```text
criminal-copilot/
├── README.md                          # Project overview, setup, and usage guide
├── app.py                             # Stage 4: Streamlit web application
├── data/
│   └── mock_investigation_data.json   # Clearly labelled FICTIONAL mock data (temporary layout)
├── src/
│   ├── __init__.py                    # Package marker
│   ├── evidence_search.py             # Stage 2: Evidence retrieval engine & exact calculations
│   ├── investigation_assistant.py     # Stage 3: Local-LLM (qwen2.5:3b) Q&A assistant
│   ├── ui_helpers.py                  # Stage 4: UI filtering & formatting helpers
│   └── validate_data.py               # Schema-flexible JSON validator & privacy-safe summarizer
└── tests/
    ├── __init__.py                    # Test package marker
    ├── test_evidence_search.py        # Unit tests for Stage 2 evidence retrieval engine
    ├── test_investigation_assistant.py # Unit tests for Stage 3 assistant (offline with mocks)
    ├── test_ui_helpers.py             # Unit tests for Stage 4 UI helpers
    └── test_validate_data.py          # Unit tests for JSON validation, counts, and PII protection
```

---

## Prerequisites & Environment Setup

- **Operating System**: macOS (Apple Silicon, 8 GB RAM)
- **Python**: Python 3.9+ with Streamlit installed (`streamlit`)
- **Local LLM**: Ollama running locally with `qwen2.5:3b` (`ollama run qwen2.5:3b`)

---

## Usage

### 1. Launch the Streamlit Web Application (Stage 4)
From the root directory (`criminal-copilot/`), run:

```bash
streamlit run app.py
```
*(Or via Anaconda Python: `/opt/anaconda3/bin/streamlit run app.py`)*

This launches the interactive investigation workspace featuring:
- **Data Source Selection**: Toggle between the default mock dataset and **Upload Custom JSON File** to inspect any valid team JSON dataset locally.
- **Case Selection**: Dropdown dynamically populated from loaded/uploaded records, enforcing strict case boundaries.
- **Deterministic Python Metrics**: Exact record counts, recorded USD totals, and missing citation counts.
- **Evidence Search & Filters**: Text query and record-type filters with citation coordinates.
- **AI Investigation Assistant**: Grounded Q&A via local Ollama `qwen2.5:3b` in 4 structured sections.
- **Chronological Timeline**: Verified ISO timestamps with undated records placed at the end.

### 2. Run the JSON Validator and Summarizer
```bash
python3 -m src.validate_data data/mock_investigation_data.json
```

### 3. Run the Evidence Retrieval Demonstration
```bash
python3 -m src.evidence_search
```

### 4. Run the Local-LLM Assistant CLI Demonstration
```bash
python3 -m src.investigation_assistant
```

### 5. Run All Automated Unit Tests
Run all 51 automated tests offline (requires zero external network or active Ollama daemon):

```bash
python3 -m unittest discover -s tests -v
```
