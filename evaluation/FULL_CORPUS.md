# Full corpus validation — 12 November 2026

Status: PDF integrity, full parsing and database checks completed. Live full hybrid preparation stopped on Gemini quota after six completed batches (96 vectors). Full-corpus chat was correctly skipped; end-to-end acceptance is blocked.

## Completed checks

- All 12 pinned PDF SHA-256 values verified; all 13 evaluation source pages/anchors verified.
- Evaluation schema: 40 cases, source/version pins and requirement references valid.
- Offline runtime: 235 tests and 79 subtests passed; 98 structural/design assertions passed.
- Real Gemini embedding prerequisite passed: one call, one 768-dimensional vector, zero retries.
- Full parser: 6921 passages from all 12 specifications; 2710 flagged unreadable and excluded from answer evidence. SQLite integrity and foreign keys passed.

| Specification | Parsed passages | Excluded |
|---|---:|---:|
| 38.201 | 48 | 13 |
| 38.202 | 70 | 24 |
| 38.211 | 666 | 453 |
| 38.212 | 1088 | 438 |
| 38.213 | 1069 | 750 |
| 38.214 | 1140 | 467 |
| 38.215 | 148 | 69 |
| 38.300 | 1051 | 126 |
| 38.314 | 143 | 97 |
| 38.321 | 1099 | 194 |
| 38.322 | 173 | 37 |
| 38.323 | 226 | 42 |

## Retrieval findings

Natural development questions searched against the whole lexical index, with no gold clause/specification filter: **6/9** had every expected clause in the first 12 results. T03, T13 and T16 missed at least one required clause. This diagnostic does not tune or score the locked set. Hybrid ranking is a separate test.

- T03: Hinglish numerology question; expected clause exists as readable content but was not found in top 12 by raw lexical search. Runtime A can reformulate searches, so this is a retrieval diagnostic, not a measured chatbot-answer failure.
- T13: TS 38.211 clause 4.4.4.1 is marked unreadable because the mathematical glyph/order is corrupted during extraction. The raw parse cannot safely establish the complete resource-block definition. Embeddings cannot repair missing/corrupt source evidence.
- T16: MAC/PDCP comparison needs two clauses; lexical top-12 did not retrieve both. Both expected clauses are present and readable.

## Live full-corpus result

**BLOCKED: `PROVIDER_QUOTA`.** Six 16-passage batches succeeded (96 of 4,211 eligible passages). The next request was rejected with HTTP 429; no automatic retry was performed. The exact per-minute/day quota subtype is not exposed by the current runtime adapter, so this result does not establish when capacity resets. No partial index was activated. Full-corpus chat and semantic retrieval quality were not tested.

The [saved progress artifact](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/43142078528/artifacts/13910396903) retains the database/report for seven days. The manual workflow accepts `resume_run_id=43142078528` to restore completed batches, but should only be resumed once quota capacity is available. Resuming immediately at unchanged pacing may hit the same quota again. A local embedding model is a possible future solution to this external dependency; it is not implemented or silently substituted here.

## Reproducible full-corpus run

[Full corpus validation run](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/43142078528) downloads/verifies all originals, parses them, prepares the full hybrid index, then submits one actual A–B–C chat only if the complete index is ready. Preparation has a 600-second embedding deadline and maximum 500 batch attempts, with no automatic retries; provider failures stop immediately. Completed batches and the report are retained as the `full-corpus-validation` Actions artifact for seven days. No PDF/database is committed to Git.

Full domain acceptance remains open: excluded equations/tables, hybrid retrieval coverage, representative answer accuracy and sustained quota behavior must not be described as fully verified. The earlier single-excerpt demo remains separately verified.
