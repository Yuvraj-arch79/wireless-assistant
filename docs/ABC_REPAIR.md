# Restore the documented A → tools → B → C flow

This supersedes the temporary `fix_clause_flow.py` bypass. A is called for exact-clause questions too: it resolves the need and requests retrieval, B alone writes, and C reviews the exact candidate and original evidence. No hardcoded technical answer or provider fallback was added.

Changes:
- A transport uses action-specific JSON Schema branches, rather than null-padded fields from unrelated actions. Original-message references use short server-bound aliases on the wire; exact hashes, offsets and IDs are restored before backend validation. Unknown aliases are rejected.
- Empty passage expansions are invalid. Expansion is excluded from the initial wire schema when no passages exist.
- The full serialized A request, schema and reserved output count toward the observed 8,000-token allowance with a 1,000-token margin. Duplicate evidence metadata is removed from tool results; original question and clarification replies remain intact. B/C still receive complete evidence. A request that cannot fit stops before network dispatch; HTTP 413 is not retried unchanged.
- Clarification must identify a material user-detail/history gap tied to known requirements. Prompts prohibit asking users to choose factual answers or reconfirm requested language, analogy or citations. This structural check cannot prove all model clarification choices are semantically necessary.
- B is instructed to explain in the requested language, use clearly labelled faithful analogies, and disclose unsupported rationale. C still checks every factual claim and the exact candidate.
- Mixed-profile operation deadline is 60 seconds (run remains bounded to 300 seconds); HTTP read deadlines are 45 seconds for B and 30 seconds for A/C, connect 8 seconds. Provider timeout/status messages identify the role. Dispatch/result logs contain no keys or prompt/response bodies. External provider availability is not guaranteed.
- Runtime tokenizer initialization refuses an absent/corrupt local cache immediately, avoiding a hidden download during a request. Installer initializes it in a separate process with a 35-second deadline.

The one shared format repair, bounded retries, original source/version bindings, cancellation/recovery and two correction rounds remain in place. Keys, billing, model choices and PDF/index content are unchanged.

## Windows local patch

Stop the server. In the existing project PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install "tiktoken==0.14.0" "jsonschema==4.26.0" pytest
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\fix_abc_flow.py"
```

The installer modifies the affected provider functions and small engine/prompt/config sections, preserves unrelated code, saves a timestamped backup and restores its edits if checks fail. It supports the prior budget wrapper and clause bypass. An unrecognized patch location stops before writing. Do not rerun the superseded installers.

After `ABC FIX INSTALLED`, restart in the same PowerShell containing the already-tested environment keys:

```powershell
.\.venv\Scripts\python.exe -m wireless_assistant.cli --data-dir "$env:USERPROFILE\Downloads\dataone-pdf-ready" serve
```

Use **New chat** and the original TS 38.201 clause 4.2.3 Hinglish question. Logs must show A dispatch; B writes; C must accept before an answer is released. A successful API response alone is not an accepted answer. When provider capacity is being paced, a new HTTP log entry will not appear until dispatch.

## Verification and limits

13 November 2026: 258 offline tests passed, 79 subtests passed, 1 optional browser test skipped. Tests cover A being retained, retrieval/B/C handoff, rejection preventing release, clarification repair, aliases/invalid IDs, empty expansions, budget overflow/no dispatch, B/C preservation, HTTP 413/no retry, timeout privacy, cancellation and shared bounds. The installer is separately rehearsed against the old budget wrapper and clause bypass, including a second installation and preservation of an unrelated local edit.

No live provider keys were available in the repair environment. This is not a claim of live Hinglish answer quality or provider availability; the local live acceptance check remains required. CI on Windows and the optional browser suite must still pass before merge.

## Groq compiler rejection: multiple discriminator candidates

The live November 13 error reported `invalid_request_error`, parameter
`response_format`, path `/properties/result/anyOf`, with
`discriminator_multiple_candidates` naming `action` and `intent_relation`.
This is a schema compilation rejection before generation, separate from the
prior `json_validate_failed` and 413 budget errors.

Only `action` remains an enum discriminator in the A action union. The shared
`intent_relation` is a wire string with allowed values in its description;
the original backend DTO still rejects unknown values. Initial and post-search
request schemas are tested for one unambiguous enum discriminator per object
union. Strict output mode, the repair bound, original-reference checks and C
review remain unchanged.

For an already installed ABC flow, download `scripts/fix_groq_schema.py`, stop
the server and run from the project PowerShell:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\fix_groq_schema.py"
```

This patches only the known schema location and appends its regression test,
backs up both files, preserves other edits, and rolls back if offline checks
fail. It then attempts one bounded A call using existing configured Groq
environment variables. No key is displayed, no retry is performed and no draft
is published. `--offline-only` skips this call. The live probe distinguishes
HTTP acceptance from DTO validity and requires `collect` for the explicit
source question. A successful probe does not establish B/C or final-answer
quality; the actual chat must still produce a Reviewed answer with sources.

The full `fix_abc_flow.py` installer also includes this correction. Offline
JSON Schema validation alone cannot emulate Groq's compiler; live acceptance
was not tested in the patch author's environment because provider keys were
not available.

14 November 2026 verification: 267 offline tests and 79 subtests passed; one
optional browser test skipped. Evaluation manifest checks (40 cases), 98 design
assertions, dependency consistency and whitespace checks passed. The targeted
installer was run against the previous schema with an unrelated local edit;
15 schema/budget tests passed and that edit was preserved. Separate tests cover
idempotence, refusing an unknown patch anchor, rollback after failed checks,
one-attempt live diagnostics, private error reporting and rejecting an invalid
DTO even after HTTP 200. Windows/browser CI and real provider output remain
separate acceptance checks.

### GitHub-hosted live acceptance

Repository secrets can be used inside Actions without exporting their values to
the repair workspace. `abc-repair-live.yml` runs on the repair branch only for
an explicit `[abc-repair-live]` workflow-file commit, or by manual dispatch. It
restores the successful November 12 public corpus artifact, verifies the pinned
source/build, and runs one Hinglish question through the actual controller with
at most seven generation attempts, one format repair and no provider retries.
Only the public evaluation report is uploaded. The final released answer must
also be inspected for language and analogy quality; HTTP 200 alone is not a pass.
The pinned artifact expires November 19; later runs need a verified replacement.

## 14 November 2026 live acceptance (GitHub Actions, existing secrets)

Run on `fix/restore-abc-flow` from checkpoint `4348555`. Each run is one
question, max seven generation attempts, one shared format repair, no retries.
No key, model, billing or local PDF/index change.

Findings, in order (each fixed with a regression test in
`tests/runtime/test_b_missing_allowance.py` that fails on the prior engine):

| Run | Stage reached | Exact failure | Fix |
|---|---|---|---|
| 43616626693 | A, retrieval, A, B (all HTTP 200) | B `request_missing_info` while the round allowance was spent but B was told `closing_mode=false` → INABILITY, no C | B payload carries `missing_info_allowed`; `closing_mode` reflects the spent allowance; a disallowed request is a contract error under the existing repair |
| 43617092806 | diagnostics | Retrieval is correct: rank 1 is the complete clause 4.2.3 (one 713-char passage, page 9, LDPC + Polar); A preview 800 chars | none needed (key-free probe `evaluation/abc_corpus_probe.py` added) |
| 43617519760 | B | B asked the user "one combined or separate analogies?" on a clear request | B `user_detail`/`history` requests must target gaps A recorded; presentation choices are B's |
| 43618328836 | B | B requested "clause 4.2.3 full text" although it was complete in evidence | Engine computes `complete_clauses`; re-requesting one is a contract error (no A round trip) |
| 43619330855 | B | `cannot_answer` claiming "only a short excerpt" of 4.2.3 (evidence and Polar text confirmed in B's request body; 6077 prompt tokens counted) | Same check applied to `cannot_answer` source/context_limit reasons |
| 43619590843 | B repair | Repaired Hinglish draft was correct (LDPC with 2 base graphs and segmentation; Polar for PBCH/control) but degenerated into a citation-marker loop `[299] [300] …` and stopped at `finish_reason=length` (2000/2000) → PROVIDER_INCOMPLETE, nothing released | **Open.** Raising the token cap would not fix a loop |

Status: **not passed.** No C-reviewed answer has been released yet. The
remaining blocker is output reliability of the free B model
(`nvidia/nemotron-3.5-super-vl:free`): across runs it asked unnecessary
questions (analogy layout, Devanagari vs Roman script), falsely reported the
supplied clause as missing, and looped. The controller now rejects each of
these without releasing anything, but the single repair can still fail. Next
options need an owner decision: a B repetition/frequency penalty (if the
OpenRouter route supports it with `require_parameters`), a different B model,
or a further structural guard. CI (Linux + Windows): 280 passed, 79 subtests.

`WA_PUBLIC_EVAL_DIAGNOSTICS=1` (Actions only) now also prints A preview
length, retrieval passage metadata, B's non-draft outputs, and for B the
request evidence IDs, provider token counts, finish reason and a bounded
excerpt of the public-question output. No keys or request headers are logged.
The Windows installers (`scripts/fix_*.py`) do not yet include these engine
changes; regenerate them once live acceptance passes.

## 15 November 2026: B on free Groq, owner-approved bounds

Owner decisions: B moved from free OpenRouter `nvidia/nemotron-3.5-super-vl:free`
to free Groq `openai/gpt-oss-20b` (existing `GROQ_API_KEY`; Mistral's API needed
prepaid credits, so it was not used). Groq profile `max_calls` is 9 in the app
and the live harness (one repair plus one C revision round); `max_repairs` stays
1; deadlines unchanged. C output prefers 2400 tokens and steps down to 900 to
stay inside the 8000-token free quota. **Chat now needs only `GROQ_API_KEY`**
(plus `GEMINI_API_KEY` for embeddings); `OPENROUTER_API_KEY` is no longer used.

Fixed from live runs (each with a regression test, mostly `tests/runtime/test_groq_b.py`):
strict schema made B invent revision entries on a first draft; gpt-oss wrote
`【1】` markers; B omitted the inline marker it declared (placed after a unique
claim anchor only); revision requests exceeded the 8K quota (alias refs,
findings-only prior review, B margin 500, output step-down); English answers or
analogies were C-accepted (language rule first for B, C blocks English sections);
Groq 400 `json_validate_failed` for B/C and empty A `failed_generation` now use
the single repair; C review truncation (output 900 → up to 2400).

Accepted, fully reviewed Hinglish answers to the acceptance question:
43709409120, 43711061439 (also 43705018556, 43707487019, 43708426820,
43708567587 before the language fix). Remaining observed risks: C occasionally
truncating (fixed after run 43710832894, not yet re-verified live), an English
"reason" sentence in 43711061439, and Groq free daily quota: on 15 Nov testing
used A's 200,000 tokens/day (run 43711499964, HTTP 429 TPD). Re-run the bounded
acceptance after the quota resets to verify the final commit.
