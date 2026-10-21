# ATLAS Dev 3 — System Limitations and Boundary Specification

> [!IMPORTANT]
> **Prototype Demonstration Scope:** ATLAS Dev 3 is a hackathon prototype demonstration built for the Smart India Hackathon (SIH) police investigation intelligence module. It is **not** production-ready software and makes zero claims of commercial or production readiness. In accordance with AGENTS.md rule 29, model training, fine-tuning, blockchain, advanced graph algorithms, CCTV/video surveillance, facial/biometric recognition, and scene-photo interpretation are explicit non-goals.

This document formally records all operational, algorithmic, architectural, and legal boundaries of the ATLAS Dev 3 document evidence pipeline per PLAN.md Section 11 and Section 12.

---

## 1. Optical Character Recognition (OCR) Boundaries

### 1.1 English-First Engine Optimization
- The extraction pipeline uses Tesseract OCR (or optionally PaddleOCR via `OCR_ENGINE=paddle`) optimized and evaluated primarily for printed English text.
- Image preprocessing filters (`synth/noise.py`, `extract/ocr.py`) apply deskewing, Otsu binarization, and contrast enhancement calibrated for English typographical structures.

### 1.2 Unmeasured Indic Script and Handwriting Accuracy
- **Handwriting:** Cursive, free-form, or handwritten field notes are out of scope. The pipeline performs no handwritten text recognition (HTR) and provides no handwriting accuracy claims.
- **Indic Scripts:** Multilingual OCR plumbing is implemented through `OCR_LANGS` (e.g., `hin`, `tam`), and missing language pack errors are caught gracefully. However, recognition accuracy on Hindi, Tamil, or other Indic vernacular scripts is **unmeasured** and not benchmarked in this release.
- **Confidence Scoring:** OCR confidence is strictly an engine-level character/word confidence score (`OcrInfo.score_kind = "engine_score_not_probability"`). It must never be interpreted as an identity probability or factual truth score.

---

## 2. Document Format and Tabular Extraction Boundaries

### 2.1 Tabular PDFs Flagged, Not Parsed
- Bank account statements, CDR records, or financial ledgers delivered as scanned or digital PDF tables are detected and flagged via `extract/tabular_pdf_detect.py` with `ReviewKind.TABULAR_PDF_DETECTED`.
- Automated table-cell extraction from PDFs is explicitly out of scope for this stage.
- **Extension Point:** Adding tabular PDF extraction requires implementing a table detection model under `src/atlas/extract/` and registering a corresponding profile parser under `src/atlas/tabular/`.
- Ingestion of structured financial and telecommunication records requires structured input formats (CSV or XLSX) with defined header profiles (`cdr_v1`, `bank_v1`).

### 2.2 Unfamiliar Spreadsheets and Header Drift
- Spreadsheets with unmapped headers trigger `ReviewKind.MAPPING_UNCONFIRMED`.
- The pipeline proposes fuzzy header alignments but strictly requires human confirmation before committing facts to the case result.

---

## 3. Entity Resolution and Heuristic Scoring

### 3.1 Heuristic Rank is Not a Probability
- All cross-case resolution suggestions output a deterministic heuristic rank (`heuristic_rank`) derived from rule weights defined in `config/resolver_weights.yaml`.
- The ranking note is mandatory on every output: `"heuristic ordering, not a probability"`.
- The score reflects weighted signal overlaps (exact identifier, phonetic name similarity, co-occurrence, attribute corroboration). It **does not represent a statistical probability**, Bayesian posterior, or identity confidence.

### 3.2 Suggestion-Only Architecture (No Automatic Merges)
- Autonomous merging of person entities is strictly forbidden (AGENTS.md rule 5).
- Every match candidate is a suggestion (`status = NEEDS_REVIEW` or `CANDIDATE`) requiring explicit authorization by a human reviewer.
- Every merge is recorded in a cryptographically hash-chained audit log and is fully reversible via the `SPLIT` action.

### 3.3 Low-Trust Identifier Isolation
- Identifiers extracted via OCR or marked with confidence below threshold are assigned `IdentifierTrust.REVIEW_REQUIRED`.
- Unconfirmed OCR phone numbers, IMEIs, and accounts are barred from autonomous cross-document or cross-case graph linkage until verified and confirmed by a human analyst.

---

## 4. Storage and System Architecture

### 4.1 Demo Entity Store is a Local Stub
- The entity store implementation in `src/atlas/resolve/store_sqlite.py` is an embedded SQLite database designed for demonstration, local evaluation, and unit/integration testing.
- It provides transaction locking and cryptographic audit chain verification for standalone execution.
- Enterprise multi-tenancy, distributed locking, distributed graph indexing, and persistent cross-case storage are external responsibilities managed by Dev 2 (API/Orchestration) and Dev 4 (Knowledge Graph).

### 4.2 Content-Addressed Originals Storage
- Original evidence files are stored immutable and content-addressed at `data/originals/{sha256}`.
- On Windows systems, write protection is enforced via `stat.S_IREAD` and tested via write denial (`PermissionError`). This ensures file integrity within the OS boundaries but does not replace enterprise Write-Once-Read-Many (WORM) hardware storage.

### 4.3 API Authentication & Access Control Boundaries (Demo Stub)
- The bundled FastAPI interface (`src/atlas/api/`) uses an `X-Atlas-User` header lookup against `config/demo_users.yaml` with a default fallback to `demo_analyst` for local demonstration and automated contract testing.
- **Bound to Localhost:** The API is intended exclusively for local prototype evaluation (`127.0.0.1`) and must never be exposed to public or untrusted networks without an enterprise API gateway.
- **Production Preconditions:** Real-world deployment requires replacing this demo stub with server-validated OAuth2/mTLS authentication, signed JWT tokens, strict principal derivation, and explicit case-to-document authorization policies.

---

## 5. Large Language Model (LLM) Integration

### 5.1 Strict Synthetic Data Guard
- The pipeline enforces `ATLAS_SYNTHETIC_ONLY=true` by default.
- Live LLM adapters (`groq`, `openai`, `gemini`) verify file checksums against `data/synthetic_manifest.json` before sending prompts. Any file not registered in the synthetic manifest is refused with `RefusalError`.
- Live API calls are permitted exclusively on synthetic test fixtures. Real operational data or PII must never be transmitted to external API endpoints.

### 5.2 Deterministic Provenance Verification
- Document text is treated strictly as untrusted data, never instructions (AGENTS.md rule 3).
- The LLM cannot create citations. All line, page, row, bounding box, and provenance coordinates are computed by code.
- Any model-proposed fact whose verbatim quote cannot be verified in the source document unit is rejected (`RejectionKind.UNVERIFIED_QUOTE`).

---

## 6. Legal and Compliance Preconditions

### 6.1 Cryptographic Hashes are Integrity Evidence, Not Admissibility Proof
- SHA-256 intake receipts, content-addressed storage, and append-only audit chains (`verify_chain()`) provide mathematical proof of data integrity and non-tampering from the moment of intake.
- However, cryptographic hashing alone does **not** constitute legal certification of evidence admissibility under Indian legal frameworks (e.g., Section 65B of the Indian Evidence Act, 1872 or corresponding provisions of the Bharatiya Sakshya Adhiniyam, 2023 / BSA).
- Proper chain-of-custody documentation, police officer certification, and forensic handling protocols remain mandatory legal prerequisites.

### 6.2 Digital Personal Data Protection (DPDP) Act Compliance
- The Digital Personal Data Protection Act, 2023 (DPDP Act) and applicable law enforcement data processing exemptions require formal legal and privacy impact assessments prior to any real-world deployment.
- Deployment on non-synthetic data requires:
  1. Formal authorization by a competent law enforcement authority.
  2. Data protection and privacy impact assessment.
  3. Role-based access control (RBAC) audit and logging.
  4. Data retention and scheduled deletion policies.
  5. Air-gapped or on-premises deployment of all OCR and LLM extraction infrastructure.

---

## 7. Change Control and Upgrades

- **OCR Engine Swapping:** Install `paddleocr` extra and run `scripts/ocr_benchmark.py` to compare accuracy against Tesseract.
- **LLM Provider Swapping:** Configure `LLM_PROVIDER` and `LLM_MODEL` in `.env` without modifying application code.
- **Contract Changes:** Changes to frozen contracts in `src/atlas/contracts/` require formal submission to `docs/CONTRACT_CHANGE_REQUESTS.md` and approval by the orchestrator.
