# Evaluation Report (Measured Pipeline Accuracy)

> **Provider**: Scripted Mock Provider (Baseline Measurement)
> **Fixture Set**: Synthetic test cases (`tests/fixtures/*.truth.json`)

> The numbers below are the deterministic **mock-provider baseline** used for regression, not a
> measurement of a live model. Live-provider behaviour is recorded qualitatively in
> `docs/DECISIONS.md` (DEC-027 to DEC-033): live providers are only reachable when `LLM_MODEL` is set
> explicitly and the file is registered in `data/synthetic_manifest.json`, so the same fixture set can
> be re-measured against a live provider with `python -m atlas eval --truth-dir data/synth`.

Metrics measured comparing pipeline outputs against synthetic ground truth fixtures under deterministic review rules:

| Case ID | Mentions Precision | Mentions Recall | Mentions F1 | Exact Match ID Acc | Quote Rejection Rate | OCR ID Review Rate |
|---|---|---|---|---|---|---|
| CASE-A-001 | 0.67 | 0.45 | 0.54 | 0.42 | 0.28 | 1.00 |
| CASE-B-002 | 1.00 | 0.62 | 0.77 | 0.25 | 0.33 | 1.00 |

### Audit & Integrity Observations
- **Mock Provider Honesty**: Baseline metrics reflect the deterministic scripted mock provider responses.
- **Quote Rejection**: Quotes not precisely locatable in unit text are strictly rejected by the validator to prevent hallucinated citations.
- **Review Queue Routing**: Unconfirmed table headers, low-confidence OCR digits, and inferred roles are automatically routed to human review.

*Note: Quality numbers are measured against synthetic fixtures and never claimed for real unmeasured handwriting/Indic data.*
