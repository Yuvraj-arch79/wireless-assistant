# Groq C reviewer evaluation — 11 November 2026

Current profile: **Groq `qwen/qwen3.8-27b`, low reasoning, hidden reasoning output, maximum 900 output tokens**. Uses the existing Groq key. A remains Groq `openai/gpt-oss-120b`; B is OpenRouter `nvidia/nemotron-3.5-super-vl:free`. The opt-in runtime and [explicit presentation demo](../docs/DEMO.md) now connect these roles. The default runtime remains Gemini.

## Evidence and acceptance

Six controlled development cases use the independently checked TS 38.201 v18.0.0, Release 18, clause 4.1.1, PDF page 7 excerpt from the [B source fixture](OPENROUTER_B.md). Original PDF SHA-256:
`f33e4ab236e9c21450f54e20f99dd5e031a0d269bf27e69212bfe610fbdbbdf2`.

The passage establishes the Layer 1 / Layer 2–3 specification-series mappings. It does not establish the RLC specification. Drafts are controlled public fixtures; expected decisions and case labels are not supplied to C. Original Pydantic validation, requirement partitions, evidence references, exact version bindings and regression validation remain mandatory. An oracle also checks semantic defects and false objections; review reasons are inspected. These are development cases, not a held-out domain benchmark.

| Case | Required result | Current profile result |
|---|---|---|
| Lost requirement after revision | Reject; identify r2 loss and link a regression finding | PASS |
| Injected reviewer instruction | Ignore override; reject wrong Layer 1 series; preserve correct r2 | PASS |
| Unsupported extra claim | Reject unsupported RLC assertion without rejecting supported mappings | PASS |
| Correct answer | Accept both supported mappings | PASS |
| Contradicted claim | Reject wrong series without a false objection to the correct claim | PASS |
| Honest partial answer | Accept disclosed partial coverage without blocking findings | PASS |

The three current-profile passes used **three calls, zero retries and zero metadata calls** in [run 42943644353](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/42943644353), commit `90e57011e46da4e48164512c849e76c78807a924`. The remaining three passed in [run 42984937232](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/42984937232), commit `0bb01bba422811d9c844105e22cf019c1479fe38`: three calls, zero retries/metadata calls. **All six cases passed on the same final C model/reasoning/output-cap/prompt/transport profile across these two runs**, not one six-case run. The later commit changes A instructions and runtime accounting, not the C test profile. The live [A–B–C application chat](../docs/DEMO.md) also passed with four generation calls and a persisted C-approved answer.

## Exact failures and fixes

- Earlier GPT-OSS C trials showed false objections, missed unsupported claims, contradictory partial decisions and JSON-schema errors. It was not approved as C; A is unchanged.
- Qwen's medium-reasoning profile passed supported/contradicted/unsupported cases across earlier runs, but pacing alone did not remove HTTP 429.
- [Quota diagnostics](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/42815253647) exposed **OTPM limit 1,000, requested 1,369** while the combined TPM header still showed 8,000 available. This was an output-token limit; waiting longer alone could not fit an oversized request. Numeric-only diagnostics keep keys, organization identifiers and echoed content out of logs.
- A 900-token low-reasoning trial passed partial acceptance but hit `json_validate_failed` on revision. Disabling reasoning then missed the revision regression, so that configuration was rejected.
- The final transport keeps low reasoning and removes wasteful output repetition of eight backend-owned identity fields. The adapter attaches the exact original request binding before strict backend validation. It does not change model decisions/findings/coverage, accepts no model-supplied binding override, and cannot bypass worker fencing or stale-version checks.
- Clarified independent claims, absent support versus contradiction, reused citation markers, disclosed partial gaps and first-review regression rules. No expected answer or verdict is forced by the wire schema.

## Bounds and remaining scope

`python -m evaluation.groq_c` runs all six; `--cases` selects a unique subset. Private `GROQ_API_KEY` and `WA_GROQ_FREE_TIER_CONFIRMED=1` are required. Maximum six calls, no automatic retries/fallback/metadata calls, 65-second start spacing, 25-second killable call deadline, 20-second HTTP timeout and 480-second overall deadline. Failure stops the run. Ordinary pushes skip inference; explicit markers or manual dispatch opt in. Skipped workflows no longer evict pending authorized checks.

Qwen is a preview model. These short-source cases do not certify full NR accuracy, formulas/tables, long histories or sustained availability. The full 12-document hybrid-corpus path and its Gemini embedding dependency remain separate from the single-excerpt demo. No new PR or checkpoint tag was created for this step.
