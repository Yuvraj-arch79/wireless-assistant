# Live provider readiness

Run `python -m evaluation.readiness` from the repository root after installing
`requirements.lock`. The [GitHub workflow](../.github/workflows/provider-readiness.yml)
also runs on relevant main-branch changes or manual dispatch. It never runs with
secrets on pull requests. Keys are available only to the probe step.

This is the first gate before the full 40-case evaluation: distinguish missing
credentials, inaccessible models, quota/network failure and malformed responses
before spending a comparison budget. It is not the full benchmark or a winner
selection. Runtime adapters/assignments remain unchanged (Gemini only).

Repository Actions secrets: `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`.
Metadata requests do not generate answers. Free-only inference confirmation is
**per provider**: `WA_GEMINI_FREE_TIER_CONFIRMED`,
`WA_GROQ_FREE_TIER_CONFIRMED`, `WA_MISTRAL_FREE_TIER_CONFIRMED` must be `1`
for the corresponding provider. The evaluation no longer uses the global flag;
the application's separate existing runtime flag is unchanged.

The owner confirmed Gemini Free tier on 2 November 2026 and authorized its test.
The workflow records that confirmation for Gemini only. Set the Gemini repository
Actions variable to `0` to revoke it if billing changes. Groq/Mistral have no
implicit confirmation. Keys remain secrets; confirmation/model settings are variables.

Automatic runs and manual default runs now select **Groq only**, inject only its
key, and make at most two requests. Select a different provider or `all` in the
manual workflow only when needed. CLI equivalent:
`python -m evaluation.readiness --provider gemini` (set the provider-specific
confirmation locally). The CLI default remains `all`; report `complete` applies
only to its recorded selected providers, never to untested providers.

Optional Actions variables: `WA_EVAL_GEMINI_MODEL`, `WA_EVAL_GROQ_MODEL`,
`WA_EVAL_MISTRAL_MODEL`. Defaults are listed in `providers.py` and checked against
each provider's model metadata endpoint before generation. Mistral's `latest`
alias is a readiness candidate, not a reproducibly pinned benchmark winner.
No model substitution occurs on failure. Metadata availability does not prove
generation quota, price or model quality.

The one-trial smoke uses development case B01 with no corpus evidence, the
production A instruction/schema and a synthetic original-message reference.
Only user input reaches A; no gold labels or expected sources. It checks schema,
clarify action and original-reference binding. It is a reduced isolated A input,
not a complete production run. No B/C, tools, embeddings or retrieval execute.
A schema pass does not establish that the question is a useful clarification.

Limits: 3 providers, at most 6 HTTP calls (one metadata plus one inference each),
zero retries, 25 seconds per killable call, 180 seconds total active budget,
2 MiB response cap and 2,000 output tokens per generation. Workflow timeout is
6 minutes including setup. No redirects, paid fallback or provider-controlled
tool execution. Provider order is shuffled with a fixed recorded seed.

The Actions summary contains only fixed provider identifiers and sanitized
status codes. No raw responses, authorization headers, API keys or reasoning
are printed/uploaded. `data/evaluation/readiness.json` contains configuration
identity, suite/prompt hashes, limits and timings locally; it remains ignored.
The workflow summary is retained with the exact commit/run. Missing/blocked and
failed calls stay in the report and make the readiness job fail.

After readiness passes: add production Groq/Mistral selection adapters and an
end-to-end fixture executor, run the preregistered development trials, calibrate
source-linked grading, then freeze configuration before locked evaluation.
Do not select A/B/C roles from this one ambiguous-question smoke.

Official contracts checked 2 November 2026:
[Gemini models](https://ai.google.dev/api/models),
[Groq API](https://console.groq.com/docs/api-reference),
[Mistral models](https://docs.mistral.ai/api/endpoint/models),
[Mistral chat](https://docs.mistral.ai/api/endpoint/chat).

## Optional Gemini diagnostic mode

Manual workflow mode `diagnostic` compares a tiny JSON request and A's production schema
on three prespecified profiles: configured baseline/default thinking,
Gemini 3.8 Flash/low thinking, and Gemini 3.1 Flash-Lite/minimal thinking.
The latter two are isolated diagnostic alternatives, not production fallback.
Official parameter contract: https://ai.google.dev/gemini-api/docs/generate-content/thinking

At most 15 requests, 300 seconds total, 25 seconds per killable call, unchanged
20-second HTTP timeout and no retries. A successful profile needs metadata, tiny
JSON and three A trials to pass. Failed A profiles are not repeated. Auth/quota
stops further requests. All observations, including failures, remain in the Actions
summary. Only status and duration are printed, never response bodies or reasoning.
`python -m evaluation.gemini_diagnostic` reproduces the diagnostic locally with
Gemini-only secret and confirmation. Workflow timeout is 10 minutes with setup.
Existing two-call readiness remains available via its CLI and for other providers.
A passing diagnostic does not validate B/C, domain answers or a production change.

The initial diagnostic (PR #19) found baseline tiny/A read timeouts, a low-thinking
tiny HTTP error and A read timeout, and 2.5 Flash generation 404s despite metadata
access. The next bounded diagnostic verifies `generateContent` capability before
inference, exposes only numeric HTTP status, and replaces the rejected 2.5 probe
with the documented 3.1 Flash-Lite minimal-thinking candidate. No working profile
or root cause is assumed from metadata alone.

## Verified readiness configuration — 2 November 2026

[Live diagnostic](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41421674256/job/125198428522):
Gemini 3.8 default thinking returned a tiny-request read timeout and an A HTTP 503;
low thinking returned HTTP 503 for both. Gemini 3.1 Flash-Lite/minimal passed
metadata, tiny JSON and all three A trials (about 3.3 seconds each).
This points to availability/latency of the tested 3.8 configuration in this run,
not a demonstrated prompt-size defect; the provider's internal root cause is unknown.

Normal readiness now explicitly defaults to `gemini-3.1-flash-lite` with minimal
thinking. This is an evidence-based evaluation configuration, not an automatic
fallback or a final A/B/C assignment. Explicit model variables still override it;
no settings are silently changed after failure. Default workflow runs return to
normal two-call readiness; the diagnostic matrix is manual-only. Original
failures remain in Actions history. Production runtime model defaults, B/C and
technical-answer quality remain unvalidated and unchanged.

## Groq migration — 2 November 2026

The owner requested Groq testing after intermittent Gemini errors. The previous
`llama-3.3-70b-versatile` returned 404; Groq's official deprecation record retires
it for free/developer tiers from 16 August 2026. Evaluation now explicitly selects
`openai/gpt-oss-20b` and verifies it against the authenticated `/models` catalog
before inference. No substitution is made when the selected ID is absent/inactive.
Reference: https://console.groq.com/docs/deprecations

Default Actions runs now select Groq, inject only its secret and retain the
per-provider guard. Groq free-plan confirmation has not been inferred from the
Gemini confirmation or the existence of its key. If the Actions variable
`WA_GROQ_FREE_TIER_CONFIRMED` is absent, metadata can run but inference remains
blocked until the account's free-only status is confirmed. Production chat is
still Gemini-only; this change is evaluation access, not a completed Groq runtime
integration or final A/B/C assignment. Readiness summaries now identify the model.

## Explicit low-call Groq test

The owner requested a low-call Groq response test under the project's free-only
constraint. `--provider groq --generation-only` makes at most one generation call
and no metadata call; the exact GPT-OSS 20B model was catalog-verified in run
41456276615. Overrides to another model fail closed in this mode. The summary
says `not_rechecked` for metadata rather than claiming a new metadata pass.

Ordinary pushes now skip API tests. Manual workflow runs or an explicit
`[groq-smoke]` merge marker are required. The authorized marker supplies the
Groq inference guard for that bounded invocation only; it is not an independent
billing inspection or a blanket plan confirmation. An explicit repository
confirmation value `0` still revokes inference. No other provider is selected.
There are no automatic retries or fallback and the call is killable after 25s
(HTTP timeout 20s). Quota/429, 503 and timeout all stop the test. A rerun would
consume another call and is not part of this one-call test. A smoke pass covers
A's schema/clarification/binding only, not the full chatbot or B/C accuracy.

The GPT-OSS 20B evaluation request uses explicit low reasoning effort and excludes
reasoning text, per https://console.groq.com/docs/reasoning . The 2,000-output-token
ceiling remains unchanged. This is not a technical-quality optimization claim.

## Groq contract result — 3 November 2026

Owner authorized GitHub use without another PR. Six HTTP generation requests were dispatched in bounded runs (2 + 1 + 1 + 1 + 1), with zero automatic retries or metadata calls. Three requests were rejected with HTTP 400; three returned content. No full chatbot success is claimed.

- Initial JSON-object response failed the duplicate-aware JSON decoder (`INVALID_JSON`); the discarded body does not establish whether the cause was syntax, duplicate keys or a non-finite value.
- Strict nested union schemas were rejected at `response_format.properties.result.anyOf`. Reordering discriminator fields did not resolve that rejection.
- A flat wire schema was accepted. Original Pydantic contracts remain mandatory after removing only null padding for unselected branches; non-null extras and unknown fields are still rejected.
- Both flat-schema live trials selected `clarify` but failed original validation: `clarify.need` (`model_type`) and `clarify.coverage_gaps` (`list_type`). Adding explicit original-contract instructions did not fix this. The wire schema permits null padding; these selected-action fields cannot be null. This remains an unresolved adapter/model contract mismatch.
- [Final single-call job](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41573961752/job/125713078037) records the sanitized result. Raw output, hidden reasoning and secrets are not logged.

`python -m evaluation.groq_contract --strict-only` makes at most one request; without the flag, the diagnostic comparison allows at most two. The Actions contract mode uses strict-only. Quota, authentication and transport failures stop immediately; each worker has a 25-second deadline. Ordinary pushes do not invoke providers.

The helper remains evaluation-only and is **not promoted into normal readiness or production chat**. Production remains Gemini-only. Groq A is not validated; B/C, real-source retrieval, domain answer accuracy and reliability remain untested. The next fix must address selected-action type constraints in the wire representation, with backend validation retained. Do not treat prompt-only instructions as schema enforcement.



## Latest Groq result — corrected strict adapter, 3 November 2026

The A clarification smoke now **passes** on `openai/gpt-oss-120b`: [live job](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41614318207/job/125843817726), 1.842 seconds, one call, zero retries. Normal Groq readiness now uses that same strict adapter and model; explicit unsupported model overrides fail closed. Production chat remains Gemini-only pending separate runtime integration and B/C evaluation.

This follow-up used five bounded requests: 20B concrete fields exposed an empty requirements list; restoring length bounds exposed overlapping primitive union alternatives; merging their allowed bounds produced an invalid JSON response on 20B; 120B passed schema/reference validation but failed clarification binding; enforcing a nonempty binding list passed on 120B. There were no automatic retries or metadata calls, and no quota error in these trials. The adapter now preserves original size/value bounds, requires concrete A need and coverage, and keeps original backend checks. Only empty out-of-scope coverage transport padding is removed; actual findings are not discarded.

The prior failed trials below/above are historical evidence, not the latest status. This is one successful A-case, not a full A/B/C benchmark, sustained availability guarantee, 3GPP technical accuracy result or account quota measurement. No provider switch or new key is currently needed for this validated A configuration. Full live B/C and production integration remain open.


## Latest B evaluation — 4 November 2026

OpenRouter `nvidia/nemotron-3.5-super-vl:free` passed six representative B cases across bounded source-backed trials: supported answer, closing refusal, open-run source request, partial disclosure, correction and injected-source instruction. See [B results and limits](OPENROUTER_B.md) for exact runs, failures, call counts and remaining coverage. This supersedes historical statements that B has not been live tested. C and production OpenRouter/UI integration remain pending. Passing this fixture does not establish broad 3GPP accuracy or sustained availability.
