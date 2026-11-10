# Groq C reviewer evaluation — 10 November 2026

Status: unsupported-claim detection passed on Qwen; five remaining cases are pending the paced continuation. This is evaluation-only. Production provider routing remains Gemini-only until explicit A/B/C integration.

C candidate: `qwen/qwen3.8-27b`, medium reasoning with hidden reasoning output, using the existing `GROQ_API_KEY`. A remains `openai/gpt-oss-120b`; B's evaluated model remains OpenRouter `nvidia/nemotron-3.5-super-vl:free`. No new key or A connection smoke is needed for this step.

## Cases and evidence

The six controlled development cases are correct acceptance, contradicted claim, unsupported extra claim, honest partial answer, lost requirement during revision, and injected reviewer instruction. They use the same pinned [B source fixture](OPENROUTER_B.md): TS 38.201 v18.0.0, Release 18, clause 4.1.1, PDF page 7. Its PDF hash and exact excerpt were independently checked in the earlier C work:
`f33e4ab236e9c21450f54e20f99dd5e031a0d269bf27e69212bfe610fbdbbdf2`.

The passage supports the layer-to-specification-series mappings, but does not establish the RLC specification. Drafts are controlled fixtures, not newly generated B responses. Opaque IDs avoid revealing test labels. Expected case decisions are withheld; generic role-policy examples explain partial acceptance. These are development checks used during refinement, not a held-out accuracy benchmark.

Original Pydantic validation, exact eight-field bindings, requirement partitions and regression validation remain mandatory. Fixture checks additionally reject missed defects and false objections to correct content. Review reasons are inspected; schema validity alone is not acceptance. C never rewrites the candidate.

## What changed

- Clarified independent claim checking, unsupported extra assertions, and the difference between absent support and explicit contradiction.
- Clarified shared citation markers: the same source applies at each marker occurrence, but each assertion still needs actual passage support.
- Distinguished disclosed source omissions from silent omissions or false coverage; partial acceptance cannot contain blocking findings.
- Removed the unnecessary C envelope. The flat C schema describes exact backend-owned bindings and the actual first/revision phase. Verdicts remain unconstrained by the test oracle.
- The backend rejects claimed regression losses/findings on a first review, in addition to existing binding, coverage and acceptance checks.
- Kept killable timeouts, finite call limits, failure stopping, zero automatic retries and no provider/model fallback.

## Observed failures

GPT-OSS 120B was not approved as C: its trials included false objections, accepting an unsupported claim, contradictory partial decisions, invalid regression metadata and provider `json_validate_failed` errors. Both strict-schema and JSON-mode comparisons retained backend validation. Earlier individual passes do not establish a reliable final GPT-OSS reviewer.

Qwen initially identified the unsupported assertion correctly but used the wrong finding category. The category definitions were clarified without weakening the expected result. It then passed that case with correct coverage and bindings in [run 42028896431](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/42028896431), including the latest inspected attempt. The next call received HTTP 429 and the run stopped. It was not a full-suite pass.

The continuation increases spacing from 40 to 65 seconds and runs only `correct contradicted partial regression injection`; the passed unsupported case is reused. This reduces bursts, but does not establish the exact exhausted quota or guarantee account availability. No automatic retry is added.

## Reproduction and bounds

Use `python -m evaluation.groq_c` for the full six, or `--cases` for a unique subset. Configure `GROQ_API_KEY` and `WA_GROQ_FREE_TIER_CONFIRMED=1` privately. The workflow's manual default remains all six. An explicit authorized `[groq-c]` marker or manual dispatch is required for inference; ordinary pushes do not spend provider quota. Confirmation value `0` disables inference.

Maximum six generation attempts, zero metadata calls/retries/fallback, 65-second minimum start interval, 25-second killable call deadline, 20-second HTTP timeout, 480-second total deadline including pacing, and 2,000 output tokens per call. Auth, quota, transport, contract or oracle failures stop the run. Only public-fixture reviews and sanitized errors are recorded.

## Remaining scope

Qwen is a preview model. Six short-source checks cannot certify broad NR accuracy, tables/formulas, multidocument retrieval, long histories, languages or sustained reliability. Groq A/C and OpenRouter B still need runtime integration, shared-quota handling and an end-to-end real-corpus/UI test. Existing checkpoint tags are preserved; no new PR is created for this evaluation.
