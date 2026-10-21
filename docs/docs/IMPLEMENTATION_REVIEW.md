# ATLAS Dev 3 — Implementation Review

**Review date:** 17 October 2026  
**Reviewed artifact:** `SFIC_Doc_Module` ZIP supplied in this conversation  
**Scope:** Static review of the implementation, tests, README and integration/limitations docs; isolated test run; Ruff and mypy checks. No project source files were changed.

## Executive assessment

This is a substantial prototype: the code is organized into ingestion, extraction, tabular parsing, provenance, consolidation, review, API and output modules; it has meaningful contract and adversarial tests; and it clearly labels itself as a hackathon/demo prototype. Ruff lint, Ruff formatting and mypy all pass.

However, the current version is **not ready for real case data or deployment beyond an isolated demo**. The most serious gaps are (1) spoofable/fail-open authorization and cross-case document access, (2) provenance verification that can publish unsupported facts as verified, and (3) unsafe ingestion/storage boundaries. The suite also has four failures after installing its documented OCR dependency, and the documented normal package installation command currently fails at the build-backend step.

## Validation performed

- `ruff check src/`: **passed**.
- `ruff format --check src/`: **passed**; 95 files already formatted.
- `mypy src/atlas --ignore-missing-imports`: **passed**; 94 source files.
- Full test suite with external provider credentials removed, mock mode forced, and Tesseract installed: **451 passed, 4 failed**.
- A normal isolated `pip install '.[dev]'` attempt failed before dependency installation: `BackendUnavailable: Cannot import 'setuptools.backends._legacy'` (see `pyproject.toml:1-3`). I installed declared dependencies separately in a temporary venv to run tests; that workaround does not fix the project's build metadata.

### Four failing tests

1. `tests/unit/test_provenance_verify.py::test_integration_scripted_mock_fir_a` — mock output refers to `DOC-fd32943c3a7a:p001`, while the current input document is `DOC-482400506952`; the verifier correctly rejects these foreign unit references. The scripted fixture/document ID pairing is stale or mismatched.
2. `tests/integration/test_pipeline_runner.py::test_clean_fir_end_to_end` — the pipeline emits **zero mentions** for the clean FIR. This is consistent with the stale mock-unit references above and contradicts the test's basic acceptance assertion.
3. `tests/e2e/test_demo.py::test_demo_scripted_review_reproduces_golden_summary` — actual Case A mention count is **9**, expected is **15**; the demo also produces **0 Case B mentions**, despite the README describing Case B facts. Fix the response/ID mismatch first; do not merely update the golden file to make the test green.
4. `tests/adversarial/test_tamper_and_concurrency.py::test_concurrent_cases_in_shared_sqlite_store_zero_contamination` — the test constructs `ReviewAction.at` and the hashed payload's `at` using two separate `datetime.now()` calls, so the entry hash does not match the stored action. Reuse one timestamp in the test, then add a genuine concurrent `apply_review_action` test; separate code review also found a real state/audit atomicity risk.

The first run initially had one additional Tesseract-environment failure; after installing Tesseract, that failure disappeared but the four failures above remained. The final four failures are not explained by a missing OCR binary.

## Stop-ship risks if the API is reachable by untrusted users

### 1. Authentication is only a spoofable demo stub

`src/atlas/api/auth.py:33-68` defaults missing/blank identity to `demo_analyst`, silently ignores auth YAML errors and grants that fallback user both demo cases. The API trusts the caller-controlled `X-Atlas-User` header; there is no actual credential validation. This is acceptable only for a tightly isolated demonstration. It is not an access-control boundary.

**Fix:** Put the API behind real server-validated authentication, fail closed on missing/bad identity and config, derive actor identity from the authenticated principal, and make demo fallback explicitly development-only. Keep it bound to localhost until then.

### 2. Review actions can be unscoped or target another case

`src/atlas/api/routes.py:95-108,320-354` makes `case_id` optional and only checks access if it is supplied. `src/atlas/resolve/review.py` similarly permits missing case scope; target IDs are not reliably checked for ownership before mutation. A caller authorized for one case may submit a mutation with no scope or targets from another case, including a merge. Actor/time are also accepted from the client (`routes.py:333-351`).

**Fix:** Require a scope for every action; load and authorize each target and both sides of a cross-case merge; derive actor/time server-side; reject client-supplied hashes; make the state mutation and audit insertion one atomic transaction.

### 3. Job and file APIs permit unauthorized access to local or cross-case evidence

- `POST /cases/{case_id}/jobs` accepts raw `file_paths` (`routes.py:75-79,204-220`) and passes them to a runner that reads and stores those paths. This is an arbitrary local-file read/import primitive if exposed.
- If no selector is provided, the job processes **every file** in the global originals directory (`routes.py:217-220`). Uploads have no case-to-document ownership record, and `doc_ids` are resolved by a global filename-prefix match (`:207-215`). One case can therefore process another case's originals.
- `GET /jobs/{job_id}` has no authentication/owner/case check (`routes.py:240-256`); raw exception strings are stored and returned to the caller (`:135-138`).
- Resolver calls permit `auth=None` (`resolve/candidates.py:73-78`), and alias retrieval is global (`:89-90`). Direct callers that omit auth can read across cases.

**Fix:** Remove `file_paths` from public requests; use server-issued upload IDs bound to a case and uploader; require an explicit authorized document list; eliminate global-original fallback; bind each job to its principal/case; authenticate status polling and return sanitized error codes; make resolver auth mandatory and scope alias lookup.

### 4. Candidate results can disclose unauthorized entity details

The API/store mask an unauthorized `candidate_case_id`, but retain candidate entity IDs, signals and explanations (`routes.py:304-315`; `resolve/store_sqlite.py:644-683`). These can disclose case-coded identifiers, names or shared identifiers even when the case field is hidden.

**Fix:** Omit the entire unauthorized candidate object or comprehensively redact every indirect identifier/signal/explanation in every output path, including graph and report outputs.

## Evidence and data-integrity risks

### 5. Verified attributes and events need evidence-to-value checks

`src/atlas/provenance/verify.py:438-478` accepts an attribute with a supported enum name even when its value is not in its quote, or when its quote is missing/unverified; it can still emit the attribute with `source=None`. It hardcodes attribute quote `occurrence_count=1`, even when repeated. At `:719-805`, an event only needs a quote somewhere in the unit; its free-text description and time are not checked against that quote. A fabricated description/time can therefore be emitted with a verified source.

**Fix:** Verify each attribute value and event description/time against the cited quote/source, record ambiguity accurately, and reject or mark unsupported fields for human review. Add adversarial tests for invented values, absent quotes and repeated quotes.

### 6. Tabular parsers can promote invalid identifiers and fabricated quotes as trusted evidence

`src/atlas/tabular/cdr.py:109-124,143-190` substitutes literal `UNKNOWN` for missing parties, accepts arbitrary strings as phone identifiers and marks them `STRONG`. The bank parser has the same missing-account/validation concern. Both synthesize a display string and label it `QuoteStatus.VERIFIED`, rather than preserving/verifying a verbatim row. If a hash is omitted, parser code fabricates a padded hash (`cdr.py:72-73`; bank equivalent).

**Fix:** Never create identifiers from `UNKNOWN`; normalize and validate phone/account/IMEI values before assigning trust; preserve the raw row/field evidence; verify exact quotes; require a validated 64-hex source hash instead of inventing one.

### 7. Hash input is not constrained before it becomes a filesystem path

`src/atlas/ingest/originals.py:31-46` lowercases/trims the caller-supplied `sha256` but does not require 64 hexadecimal characters or verify path containment before `copyfile`. A traversal-like value can make the destination escape `data/originals`; the attempted copy occurs before hash verification fails.

**Fix:** Validate exactly 64 hex characters before path construction; resolve and assert containment; reject symlinks; write atomically with exclusive/no-follow semantics.

### 8. Evidence can be extracted from bytes different from those hashed at intake

The pipeline hashes and stores the source at `runner.py:214-218`, but later extraction reads the original mutable path (`:285-350`) while provenance records the earlier hash. A file changed after the initial hash can produce extracted text attributed to a different digest.

**Fix:** Extract only from the verified content-addressed stored copy, or re-hash and reject if the source changed before/during extraction. Add a mutation-race test.

### 9. Input limits do not fail closed consistently; resource ceilings are incomplete

- PDF page/image pixel checks are inside a broad extraction exception handler (`runner.py:285-317,505-508`), which turns limit violations into warnings rather than `REJECTED_INPUT`.
- XLSX intake checks ZIP names but not total uncompressed size, member count or XML/row/cell budgets. Small compressed files can expand substantially.
- PDF page-count checks do not bound physical page dimensions or rendered pixel count; high-DPI rendering of a huge MediaBox can exhaust memory.
- PDF OCR failures may become empty page text while the document still appears processed; page warnings are not consistently promoted to document/job status.

**Fix:** Preserve a distinct rejected-input path for limits; add XLSX ZIP expansion and dimension budgets; preflight PDF page dimensions and render-pixel counts; propagate OCR failure as partial/failed with explicit review status. Test malicious compressed workbooks, huge PDF pages and over-limit images/PDFs.

## LLM and audit reliability

### 10. The configured run call cap is unused and retries can multiply

`MAX_LLM_CALLS_PER_RUN` is defined but not enforced. `runner.py:547-557` calls the retry wrapper, while provider adapters also retry; a transient failure can cause up to `max_attempts²` provider calls. This undermines cost/budget limits and can make large inputs produce many calls.

**Fix:** Enforce one per-run budget across all chunks and retries; choose a single retry owner; do not retry non-retryable provider errors; record calls, usage and explicit budget-exhaustion status.

### 11. Audit and store operations need stronger scope/atomicity

Independent review found that `record_action` trusts supplied chain fields, review mutations and audit writes are separate operations, and concurrent actions can race on the same chain tail. Store methods should also validate that each nested mention/suggestion belongs to the case key under which it is stored. The failed concurrency test itself has the timestamp-construction bug described above, so it should not be treated as proof of the concurrency defect; add a corrected test that exercises the actual review-action workflow.

## Other material gaps

- `docs/SETUP.md` and `config.py` disagree on the default Tesseract command (documented `tesseract` vs Windows path in settings).
- PDF page helpers ambiguously accept both zero- and one-based indices and can return the wrong page for a caller using 1-based indexing.
- CSV/XLSX duplicate headers can silently overwrite values; formula-looking bank amount strings can be stripped into numeric facts; timezone marker detection uses substring matches.
- Cypher export merges by global node ID and overwrites case/evidence properties, so importing overlapping IDs across cases can corrupt case scope.
- The graph/evidence API should enforce that nested records have the same case as the request.
- The documented Dev2 environment URL/token settings are not wired into the default client construction, which can silently fall back to localhost without authentication.

## Archive hygiene

The supplied ZIP includes a project-root `.env` entry (**201 bytes**) and a `.git/` directory entry, in addition to generated outputs/cache/runtime material. I did **not** open or inspect `.env` contents. If it contains real API keys or tokens, revoke/rotate them because the archive was shared; remove `.env` and private repository metadata from distributable ZIPs. Include `.env.example` only, and exclude generated outputs, caches, virtual environments and test artifacts unless intentionally sanitized.

## Recommended fix order

1. **Containment first:** Treat as local demo only. Do not use real evidence or expose the service until authentication, job ownership, case-to-document ownership and file-path selection are fixed.
2. **Case-scope enforcement:** Make case/user authorization mandatory through API, resolver, review actions, store writes, graph/evidence output and reports. Verify every mutation target and both sides of merges.
3. **Evidence correctness:** Fix mock fixture/document ID alignment and failing e2e tests; validate nested attributes/events against evidence; correct tabular provenance and identifier trust; remove fabricated hash fallbacks; extract from immutable stored bytes.
4. **Input safety:** Enforce hash-path validation, XLSX expansion/shape limits, PDF render-pixel budgets and fail-closed rejection/status behavior.
5. **LLM/audit safety:** Enforce global call budget, remove nested retries, make audit/action updates atomic and verify chain tail inside the transaction.
6. **Reproducible delivery:** Fix `pyproject.toml` build backend, run install from a clean clone, repair the concurrency test timestamp, regenerate and review golden data only after fixture/code fixes, and rerun all gates.
7. **Release cleanup:** Remove `.env`, private `.git` material, caches, `.venv`, outputs and other generated files from shared archives.

## What is already good

- Clear prototype/non-production disclaimers and sensible stated non-goals.
- Extensive structured tests; a large majority passed in the isolated run.
- Ruff, format and mypy checks are clean.
- Quote verification, strict model schemas, prompt-injection framing, SHA-256 intake receipts, HTML autoescaping and OCR uncertainty handling show sound design intent.
- Synthetic-only provider gating and explicit mock-provider honesty banner are useful demo safeguards.

**Bottom line:** Keep building from this code, but treat authorization, cross-case isolation, provenance accuracy, ingestion safety and clean-install/test reliability as the next release gate—not optional polish.
