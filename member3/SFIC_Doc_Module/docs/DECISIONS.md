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

### DEC-024: Person-name filtering is configuration-driven, not hardcoded
- **Context:** The extractor wrongly accepted generic phrases and bank narrations ("The Person", "Service Reversal", "Ordinary course of business") as PERSON. The prior fix embedded an entity blacklist and regexes directly in `normalize/names.py`, which is both brittle and violates the "nothing hardcoded, nothing predefined" requirement.
- **Decision:** Entity filtering is loaded from `config/entity_filters.yaml` (`PersonNameFilter`), with an explicit-path argument, the `ENTITY_FILTER_CONFIG` environment override, and a packaged fallback. Behavior combines lexicon membership (generic terms, role terms, narration terms) with structural rules (function words, generic prefixes, minimum letters, maximum token count). No entity-name literal appears in Python source; changing the YAML changes behavior with no code change (proved by `tests/unit/test_entity_filters_config.py`).

### DEC-025: Single retry layer and client-side pacing
- **Context:** Live Groq runs failed with 429s because the runner wrapped `execute_with_retry` around adapters that already retried internally (nested 3x3 bursts), because there was no delay between chunks, and because `Retry-After: "6s"` failed `float()` parsing.
- **Decision:** Adapters (`OpenAiAdapter`, `GeminiAdapter`) declare `handles_retries = True`; `execute_with_retry` short-circuits to a single `client.extract(...)` call for such clients, so retries happen exactly once per layer. `llm/pacing.py` provides `parse_retry_after` (handles `6s`, `1m30s`, `500ms`, HTTP dates, plain numbers) and a `RateLimiter` (sliding window + derived minimum interval + `notify_retry_after`). New settings `LLM_MAX_REQUESTS_PER_MINUTE` (30), `LLM_RATE_WINDOW_S` (60.0) and `LLM_MIN_INTERVAL_S` (0.0 = derived) control pacing; the hardcoded inter-chunk `time.sleep(1.0)` was removed from the runner. All pacing values live in configuration, not source.

### DEC-026: Development web UI is a separate, auth-free testing surface
- **Context:** There was no simple way to upload a document and inspect extracted entities and connections during development.
- **Decision:** A small self-contained page is served at `GET /` by `atlas.api.ui` (no CDN, no client-side entity lists), launched with `python -m atlas ui`. `GET /ui/config` exposes available providers and schema enum values so the page hardcodes nothing. `POST /ui/run` writes uploads to a `tempfile.mkdtemp` directory using basename-only names, runs the pipeline synchronously, and returns entities, relationships, events and a graph payload. The route is intentionally auth-free because it is a dev/testing surface only; it enforces `validate_case_id` and the size limit, and it surfaces the `SCRIPTED MOCK PROVIDER: not live extraction` banner (DEC-015) whenever the run uses the mock provider.

### DEC-027: Model-reported `unit_id` is resolved deterministically inside the chunk
- **Context:** A live Groq run (`openai/gpt-oss-120b`, 2026-10-19, `data/synth/SURVEILLANCE_A.txt`) completed in 16.5 s with **0 mentions and 14 rejections**. Every rejection was `unit_not_in_chunk`: the prompt shows headers like `[UNIT DOC-45de563df99f:p001:l000005]` but the model echoed only the trailing segment `l000005`, and `verify_model_output` required an exact match plus a `doc_id` prefix.
- **Decision:** `atlas.provenance.verify.resolve_unit_id` resolves a reported reference strictly against the units actually present in the chunk: (1) exact match wins, (2) otherwise a reference that is a unique `:<segment>` suffix of exactly one chunk unit is accepted, (3) anything matching nothing, more than one unit, or a unit belonging to another document returns `None` and the item is rejected. Resolution is reference lookup, not repair: the quote must still verify verbatim in the resolved unit and all provenance (page, lines, bbox) is computed from that unit, so no identifier, page or quote is ever invented. Applied to mentions, relationships and events. Result on the same input: 0 → **6 mentions, 2 relationships, 2 events, 1 rejection**. Tests: `tests/unit/test_provenance_unit_refs.py` (exact, unique suffix, ambiguous-`None`, foreign-doc-`None`, unknown-`None`, mention/relationship provenance).

### DEC-028: Live providers require an explicit `LLM_MODEL`; no hardcoded model fallbacks
- **Context:** Hard Rule 9 forbids hardcoding model names from memory, yet `llm/client.py` silently defaulted to `gpt-4o-mini`, `gemini-2.0-flash` and `openai/gpt-oss-120b` whenever `LLM_MODEL` was empty. The developer's `.env` had `LLM_MODEL=` empty, so the running system depended on an unverified hardcoded default.
- **Verified live (2026-10-19, Groq, installed `openai` 3.29.0):** model `openai/gpt-oss-120b` at `https://api.groq.com/openai/v1` accepts `response_format={"type": "json_schema", "strict": true}` and returned a schema-valid payload in 2.03 s (2 mentions).
- **Decision:** `llm/client.py` no longer contains any model-name literal: `_require_model(cfg, provider)` raises a secret-safe `ConfigError` naming `LLM_MODEL` when it is empty for `openai`, `gemini` or `groq`. The model id is supplied by configuration (`LLM_MODEL=openai/gpt-oss-120b`) and recorded here. Adapter constructor defaults remain only for direct adapter construction in unit tests; the live path always passes an explicit model.

### DEC-029: The dev UI offers only the providers the operator enables
- **Context:** The page offered `mock`, `groq` and `gemini` because credentials for each happened to be visible to the process, which is confusing when the deployment is "Groq only". Choosing `mock` also produced zero entities for every unscripted file, with no explanation.
- **Decision:** New setting `LLM_PROVIDERS_ENABLED` (comma-separated, empty by default) is the authoritative allow-list for `GET /ui/config` and `POST /ui/run`; when it names nothing usable the configured `LLM_PROVIDER` is offered alone. `POST /ui/run` rejects any provider outside that list with HTTP 400, and an omitted provider field falls back to `LLM_PROVIDER` instead of a hardcoded `mock`. With one provider enabled the page renders a static provider badge instead of a dropdown. `python -m atlas run --provider` now also defaults to `LLM_PROVIDER` (previously it always overrode configuration with `mock`). Local `.env` is set to `LLM_PROVIDER=groq`, `LLM_MODEL=openai/gpt-oss-120b`, `LLM_PROVIDERS_ENABLED=groq`.

### DEC-030: Registration of uploads as synthetic is an explicit opt-in in the dev UI
- **Context:** With `ATLAS_SYNTHETIC_ONLY=true` (Hard Rule 1) any file whose SHA-256 is not in `data/synthetic_manifest.json` is rejected before the model is called, so a live run on an unregistered upload returns `rejected_input` with zero entities. Nothing in the page explained that.
- **Decision:** No rule was weakened. The page now (a) publishes the run `state` as a coloured banner with a plain-language `state_note`, (b) explains the synthetic-manifest refusal and names the CLI remedy, and (c) offers an unchecked checkbox "I confirm these uploads are synthetic" which, when ticked, calls the existing attestation path (`atlas.ingest.synthetic_guard.register_synthetic_files`, the same JSON format as `python -m atlas register-synthetic`) before the run. Registration is a human declaration recorded in a git-ignored manifest, is idempotent, and remains the only way a live provider may see an uploaded file.

### DEC-031: Dev-UI run feedback, upload streaming and temp cleanup
- **Context:** A blocking request with no feedback is indistinguishable from a hang (a stopped server produced a page that appeared to load for ~10 minutes), and an upload was fully buffered in memory before the size check.
- **Decision:** `POST /ui/run` streams each upload to disk in 1 MiB blocks and aborts as soon as `MAX_FILE_MB` is exceeded (no full-file buffering), skips empty files with a warning, and uses `tempfile.TemporaryDirectory` so uploaded bytes are removed when the request finishes. The page shows a live elapsed-seconds counter and a Cancel button (`AbortController`) while a run is in flight, reports the duration in the run summary, and distinguishes `completed` / `completed_with_warnings` / `rejected_input` / `failed` in a state banner. User-facing messages never include file contents; unexpected failures return a type-only message and log the traceback through the PII-scrubbing logger. A provider error surfaces a `rejected_input` explanation rather than a silent "no output".

### DEC-032: Role/rank tokens no longer discard a genuinely named person
- **Context:** The config-driven filter (DEC-024) rejected any PERSON whose surface text contained a role token, so the real named officer "Sub-Inspector K. Rathore" from `data/synth/SURVEILLANCE_A.txt` was dropped as a `schema_violation`.
- **Decision:** Narration vocabulary still rejects a phrase outright (real names never contain "reversal", "deposit", "ordinary"). A role token now rejects the phrase only when no genuine name token remains, so bare roles ("Investigating Officer", "Inspector K") are still refused while "Sub-Inspector K. Rathore" and "Officer Ramesh Kumar" are kept; the role itself is captured separately in `stated_role`. Behaviour remains entirely lexicon-driven (`config/entity_filters.yaml`) with no entity strings in source. Tests: `tests/unit/test_person_name_roles.py`.

### DEC-033: Run results are downloadable as JSON from the dev UI
- **Context:** Extraction results were only visible as rendered tables, so they could not be saved as a file, and the pipeline's own artifacts under `outputs/{case_id}/{run_id}/` were undiscoverable from the page.
- **Decision:** The page gained a "Download JSON" button that saves the exact payload it renders (`state`, `state_note`, documents, mentions, relationships, events, review items, rejections, warnings, graph) as `atlas_<case_id>_<run_id>.json`, serialized client-side from the last response: no second model call and no server-side run cache. In addition, `GET /ui/runs/{case_id}/{run_id}/{artifact}` serves the pipeline's canonical artifacts as file attachments (`result.json`, `review_queue.json`, `receipt.json`, `events.jsonl`, `trace.jsonl`), and `GET /ui/config` publishes those names so the page hardcodes nothing. The route validates `case_id` through the frozen contract helper, requires `run_id` to match the generated `RUN-YYYYMMDDTHHMMSSZ-<6hex>` format, accepts only allow-listed artifact names, and requires the resolved path to remain inside `OUTPUT_DIR` (defence in depth against path traversal). Verified live on 2026-10-19: a UI run (groq, `openai/gpt-oss-120b`, state `completed_with_warnings`) downloaded 22,056 bytes of `application/json` that parse back to 6 mentions, 2 relationships, 3 events and a 10-node/8-edge graph; the artifact route returned `200` with `content-disposition: attachment; filename="<case_id>_<run_id>_result.json"`. Tests: `tests/contract/test_api_ui.py`.

### DEC-034: Documentation is kept true to the configured provider; stale commands and gate statuses removed
- **Context:** Docs written before DEC-027…DEC-033 still prescribed `LLM_MODEL=mock-extraction-model` / `gpt-4o` (SETUP.md), listed only `openai` and `gemini` as live adapters (LIMITATIONS.md), showed subcommands that do not exist (`atlas extract`, `atlas ingest`, `atlas resolve`, `atlas report`, `python -m atlas.eval.runner`), and CHECKLIST.md still marked gates 4 and 5 as pending although `outputs/gates/gate_4.json` and `gate_5.json` record zero failures. README.md also linked `docs/PLAN.md` (the file is at the repository root) and ran the demo through `scripts/demo.py` instead of the documented entry point.
- **Decision:** Documents must satisfy three checks: (1) no model id is ever presented as a default — every live example sets `LLM_MODEL` explicitly; (2) every command shown is verified against `python -m atlas --help`; (3) live-provider lists include `groq`. The developer UI (provider allow-list, live elapsed counter, synthetic-manifest refusal message, JSON download and artifact links) is now documented in README.md §4.6 and docs/SETUP.md §4.4. Updated: `README.md`, `docs/SETUP.md`, `docs/MODEL_GUIDE.md`, `docs/DEVELOPER_INTEGRATION_GUIDE.md`, `docs/LIMITATIONS.md`, `docs/CHECKLIST.md`, `docs/EVALUATION.md`, `docs/IMPLEMENTATION_REVIEW.md`. `PLAN.md` and `AGENTS.md` were deliberately left untouched (orchestrator-owned and frozen after Gate 0); the divergent `PLAN.md` env-key list is reported rather than silently rewritten.
- **Also in this change (local hygiene, git-ignored only):** run residue under `outputs/` (per-case directories, `demo_summary.json`, `entity_store.db`, `ui_demo.json`, a local verify log) and an empty `tmp/` were deleted. `outputs/gates/` (gate evidence) and `data/` (synthetic fixtures, manifest, originals, receipts) were preserved so the demo still runs offline; no tracked file outside `docs/` and `README.md` was changed and no code was deleted (every module listed in CHECKLIST.md §1 was confirmed live, e.g. `llm/retry.py` is still imported by `pipeline/runner.py`).



