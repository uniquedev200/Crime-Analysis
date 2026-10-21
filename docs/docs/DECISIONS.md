# ATLAS Dev 3 — Architectural Decisions & Amendments Log

This document records architectural decisions, deviations, and environment-specific adaptations for ATLAS Dev 3.

## Decision Log

### DEC-001: Python Version Target (3.12 preferred, 3.11 accepted; never 3.14)
- **Context:** Host environment has default Python 3.14.0 and CPython 3.11.15. Python 3.14 lacks pre-compiled wheels for key C-extensions (`pypdfium2`, `opencv-python-headless`).
- **Decision:** Target Python 3.12 (or 3.11). Set `requires-python = ">=3.11,<3.13"`, `ruff` target-version, and `mypy` python_version accordingly. Python 3.14 is explicitly forbidden.

### DEC-002: Windows Tesseract OCR Configuration & Mandatory Gate Testing
- **Context:** On Windows, Tesseract is typically installed via `winget` at `C:\Program Files\Tesseract-OCR\tesseract.exe` and is not automatically in system `PATH`.
- **Decision:** Support `TESSERACT_CMD` and optional `TESSDATA_PREFIX` in `config.py` and `.env.example`. `ocr/tesseract.py` configures `pytesseract.pytesseract.tesseract_cmd`. `scripts/check_env.py` verifies the path, version, and installed languages.
- **Enforcement:** Set `ATLAS_REQUIRE_TESSERACT=true` on this development machine. When set, `needs_tesseract` tests cannot be skipped, and Gate 1 fails if the binary is absent.

### DEC-003: Deterministic Windows-Safe Identifiers and Path Traversal Defense
- **Context:** Windows paths reject `:` and `+`. Timestamps with colons break folder creation. Unvalidated `case_id` values could allow path traversal.
- **Decision:** Format `run_id` as `RUN-YYYYMMDDTHHMMSSZ-<6hex>` without colons. Introduce a safe-filename helper ensuring characters like `:` or `+` are never in directory names. Validate `case_id` in `contracts/` with `^[A-Za-z0-9_-]{1,64}$` to block traversal at Gate 0. Uploaded files are reduced to `os.path.basename` and stored content-addressed.

### DEC-004: Cross-Platform Line Endings and SHA-256 Fixture Integrity
- **Context:** Git's default Windows CRLF conversion mutates newline characters, invalidating fixture SHA-256 hashes and tripping the synthetic-only guard.
- **Decision:** Enforce `* text=auto eol=lf` in `.gitattributes`, mark fixtures and binaries (`*.pdf`, `*.xlsx`, `*.png`, etc.) as binary (`-text`), and generate all synthetic fixtures with explicit `\n`.

### DEC-005: Windows Read-Only Original Store Assertion
- **Context:** Unix `0444` file mode bit semantics do not map directly to Windows permissions.
- **Decision:** On Windows, immutability tests assert that opening an existing original for write access raises `PermissionError` (or is denied via `os.access`), rather than inspecting POSIX mode bits.

### DEC-006: Explicit OCR Engine Selection (No Automatic Fallback)
- **Context:** Automatic engine fallback risks silent non-reproducibility of OCR text and confidence scores.
- **Decision:** OCR engine is selected strictly via `OCR_ENGINE` configuration (`tesseract` default, `paddle` optional challenger). If a requested engine or language is unavailable, fail loudly with an actionable exception.

### DEC-007: Reviewer Confirmation of OCR Identifiers (`CONFIRM_IDENTIFIER`)
- **Context:** Scanned FIRs produce OCR-derived identifiers flagged `review_required`. If permanently blocked from graph nodes, cross-case demo cannot link Case A and Case B.
- **Decision:** Implement reviewer promotion action (`CONFIRM_IDENTIFIER` / `CORRECT_IDENTIFIER`). Once confirmed, `confirmed_by` is set, promoting the identifier to `strong`/`confirmed` status, unblocking unified graph node generation and cross-case resolution.

### DEC-008: Scope & Documentation Framing
- **Context:** Overclaiming "production readiness" or "customer-facing enterprise" status misrepresents a hackathon prototype.
- **Decision:** Frame all documentation, reports, and limitations as a high-integrity demonstrable hackathon prototype for SIH judges. `PLAN.md` is the single source of truth; derived summary documents must never be passed to workers.

### DEC-009: No Editable Installs & Strict Worktree Subprocess Isolation
- **Context:** An editable install (`pip install -e .`) points Python to a single `src/` directory, causing parallel worker worktrees to accidentally import `main`'s code and pass tests falsely.
- **Decision:** Never use editable installs. Install third-party dependencies only (`uv pip install -r pyproject.toml --extra dev`). Pytest configures `pythonpath = ["src", "."]`. Subprocesses run with `PYTHONPATH=<current worktree>\src`. `verify.py` verifies that `atlas.__file__` resides strictly inside the active worktree directory. CLI entrypoint is `python -m atlas` via `src/atlas/__main__.py`.

### DEC-010: Test Data Independence from Git-Ignored Directories
- **Context:** `data/` is git-ignored, so fresh worker worktrees do not have access to pre-generated test data or synthetic manifests.
- **Decision:** Unit and integration tests must not depend on git-ignored `data/`. A pytest session fixture generates the required synthetic files into `tmp_path`, creates a transient test manifest, and sets `DATA_DIR` dynamically. `python -m synth.generate` remains the standalone demo script.

### DEC-011: Strict Fixture Determinism on Local Windows Environment
- **Context:** ReportLab, OpenPyXL, and Pillow embed timestamps and metadata, and OS fonts vary across environments, causing byte/hash differences between runs.
- **Decision:** Use ReportLab `invariant=1`; pin OpenPyXL core properties and ZIP timestamps; strip/pin Pillow PDF metadata; vendor `DejaVu Sans` font into `synth/fonts/DejaVuSans.ttf` with its license. Determinism is asserted across two consecutive runs on the same machine.

### DEC-012: Enforce UTF-8 Everywhere
- **Context:** Windows defaults to `cp1252`, corrupting Hindi (Devanagari) and Tamil scripts and quote matching.
- **Decision:** All file I/O must specify `encoding="utf-8"`, JSON serialization must specify `ensure_ascii=False`, and all subprocesses run with `PYTHONUTF8=1`. Gate 0 includes a Devanagari/Tamil round-trip test.

### DEC-013: OCR Test Independence in Wave 1
- **Context:** B1's real-OCR test previously depended on D1's synthetic fixtures, which created an inter-worker dependency deadlock in Wave 1.
- **Decision:** Worker B1 renders its own clean test page using the vendored `synth/fonts/DejaVuSans.ttf` font, ensuring complete independence from D1.

### DEC-014: Machine-Verifiable Gate Evidence (`gate_N.json`)
- **Context:** Autonomous agents self-reporting "all passed" in chat cannot be trusted.
- **Decision:** `scripts/verify.py` writes machine-readable evidence to `outputs/gates/gate_N.json` containing the commit hash, clean-tree boolean, test counts, and names of skipped tests. Merging to `main` requires that the report's commit matches branch HEAD, the tree is clean, and zero tests are skipped on this machine.

### DEC-015: Honest Mock Provider Transparency
- **Context:** Demo videos recorded using scripted mock responses deceive evaluators about extraction capabilities.
- **Decision:** Whenever `run.provider == "mock"`, all outputs (HTML report, `/results`, CLI) must display the prominent banner: `SCRIPTED MOCK PROVIDER: not live extraction`. The final submitted demo video must be recorded using a live model on synthetic data.

### DEC-016: Windows Worktree Paths and Subprocess Safety
- **Context:** Windows `MAX_PATH` limitations and PowerShell quotation issues cause failures with long nested paths and shell strings.
- **Decision:** Worktrees are created at short paths `C:\w\<name>`. `git config core.longpaths true` is enabled. All subprocesses pass list arguments without `shell=True`.

### DEC-017: CLI Convention
- **Context:** The plan mixed `atlas <cmd>` and `python -m atlas <cmd>`, yet DEC-009 forbids installing the package, so no `atlas` console script exists.
- **Decision:** Every command is `python -m atlas <cmd>`. Docs, tests and reports use only that form.

### DEC-018: Optional Tests Are Deselected, Not Skipped
- **Context:** DEC-014 requires zero skipped tests, but PaddleOCR and Indic-font tests cannot run on every machine.
- **Decision:** Such tests carry the `optional` marker and are deselected by default (`-m "not optional"`). The gate file lists them under `not_run_optional`. Any other skip fails the gate.

### DEC-019: Orchestrator Vendors the Font and Test Harness in Wave 0
- **Context:** B1 (OCR) needs `synth/fonts/DejaVuSans.ttf` while D1 owns `synth/`, which would race in parallel Wave 1.
- **Decision:** The orchestrator vendors the font and license, and creates `tests/conftest.py` with a lazy `synthetic_dataset` fixture, in Wave 0. D1 implements `synth.generate.generate_all(out_dir, seed) -> manifest_path` and must not modify `synth/fonts/`.

### DEC-020: One Shared Interpreter and a Dependency Freeze
- **Context:** Worktrees at `C:\w\<name>` have no `.venv` of their own, and parallel dependency edits would conflict.
- **Decision:** All agents use the main repo's `.venv` interpreter by absolute path, with `PYTHONPATH=<worktree>\src`. `pyproject.toml` declares every dependency in Wave 0. Only the orchestrator changes dependencies afterward.

### DEC-021: PowerShell 5.1 Compatibility
- **Decision:** No `&&` in any documented command; use `;` or separate lines.

### DEC-022: AtlasSettings uses extra="ignore" not extra="forbid"
- **Context:** The `.env` file contains non-Atlas environment variables like `PYTHONUTF8=1`. With `extra="forbid"`, pydantic-settings rejected these, causing all config tests to fail.
- **Decision:** `AtlasSettings` uses `extra="ignore"` so non-Atlas env vars in `.env` are silently discarded. The `extra="forbid"` rule from PLAN.md section 4 applies to contract records (Pydantic models), not the settings loader.

### DEC-023: LLM Layer SDK Versions, Structured Output Formats, and Error Mapping
- **Context:** PLAN.md Section 5.9, Section 8 (F2 task card), and Hard Rule 9 require verifying official structured output and error handling for installed SDK versions, recording choices in DECISIONS.md, and encapsulating provider-specific schema translations inside adapters without mutating frozen contracts.
- **Environment SDK Versions Verified:**
  - `openai`: version 3.29.0
  - `google-genai`: version 2.30.0
- **OpenAI Adapter (`OpenAiAdapter`):**
  - Uses `client.chat.completions.create` with `response_format={"type": "json_schema", "json_schema": {"name": "model_output", "strict": True, "schema": MODEL_SCHEMA}}` and `temperature=0`.
  - Maps `openai.RateLimitError` (429) extracting `Retry-After` header when available, `openai.AuthenticationError` and `openai.PermissionDeniedError` (401/403) to secret-safe `AuthError`, `openai.InternalServerError` (5xx) to `ServerError`, `openai.LengthFinishReasonError` / `finish_reason == "length"` to `TruncatedOutputError`, and `finish_reason == "content_filter"` / `message.refusal` to `RefusalError`.
- **Google GenAI Adapter (`GeminiAdapter`):**
  - Uses `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=gemini_schema, temperature=0, system_instruction=...))`.
  - **Schema Translation:** Google GenAI 2.30.0 requires OpenAPI 3.0 types and rejects Draft-7 multi-type lists (e.g. `type: ["string", "null"]` raises `ValueError: ['string', 'null'] is not a valid Type`). `GeminiAdapter` encapsulates `convert_schema_for_gemini()` to convert `type: ["string", "null"]` to `type: "string", nullable: True` and cleans `None` from `enum` arrays with `nullable: True`. Frozen contracts in `contracts/model_schema.py` remain untouched.
  - Maps `google.genai.errors.ClientError` (401/403) to secret-safe `AuthError`, `ClientError` (429) to `RateLimitError`, `google.genai.errors.ServerError` (5xx) to `ServerError`, `FinishReason.MAX_TOKENS` to `TruncatedOutputError`, and safety finish reasons (`SAFETY`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `IMAGE_SAFETY`) to `RefusalError`.
- **Retry Matrix & Secret Safety:**
  - `execute_with_retry` enforces Section 5.9 retry rules: 429/5xx/timeout/connection errors retry up to `LLM_MAX_ATTEMPTS` (default 3) with base 2.0s exponential backoff and jitter, honoring `Retry-After`. Truncated output signals truncation via `TruncatedOutputError` with optional `split_fn` re-run. Schema violations allow exactly 1 retry of that chunk before raising `SchemaViolationError`. 401/403 and safety refusals fail fast with 0 retries. All error messages are guaranteed secret-safe.

