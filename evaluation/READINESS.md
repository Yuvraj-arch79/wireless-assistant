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

Automatic runs and manual default runs select **Gemini only**, inject only its
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

## Temporary Gemini diagnostic mode

The Gemini workflow now compares a tiny JSON request and A's production schema
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
