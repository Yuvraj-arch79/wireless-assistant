# Evaluation baseline 0.2.0

40 versioned cases: **16 technical questions, 18 conversation/failure scenarios and 6 reviewer challenges**. All 12 pinned specifications are represented. The split has **26 development and 14 locked cases**. This completes the initial evaluation-question specification, not a live benchmark or full SRS acceptance.

[Case data](cases.json) is the executable-data source of truth: input/history, fixture instructions, required points, forbidden outcomes, SRS references, source version/hash, clause and 1-based PDF page. PDF page numbers count the cover; they differ from printed specification page numbers. Answers are graded for meaning, not exact wording. Technical expectations were checked against original PDF text; resource-block, numerology and channel-mapping pages were also visually inspected. A named domain reviewer has not approved this candidate suite.

## Purpose and limits

Measure retrieval, answer support and control behavior separately. A supported-looking citation is insufficient; the cited passage must support the associated claim, including conditions and units. The cases intentionally include the known unreadable resource-block extraction gap. Do not remove hard cases to improve the score.

The scope is an initial small, mostly introductory baseline, with selected conditions/tables. It is not representative coverage of every PHY/MAC procedure, LDPC/polar coding, random access, beam management, scheduler configuration, ASN.1 or all 94 requirements. Add domain-reviewed harder cases before pilot acceptance. Behavioral fixtures are specifications for the future harness, not a claim that these exact cases have already been run.

Public practices informing the design: [OpenAI evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices) and [Anthropic agent evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents). We apply task-specific rubrics, varied cases, repeated trials and review of actual outcomes. This is an application evaluation, not a reproduction of any company's internal model-training benchmark.

## Split discipline

- Use `dev` for prompts, parser fixes and role/provider selection. Keep related source clauses and question families together.
- Freeze code, prompts, parser, corpus build, provider/model IDs and configuration before running `locked`. Do not choose the winning provider using locked results and call those same results unbiased final validation.
- Locked means reserved by process, **not private or proven uncontaminated**: these cases are public in GitHub, and their authors have seen the labels. Keep gold points and reviewer outcomes out of all tested role prompts and the technical retrieval corpus. Only user messages, declared history and explicitly supplied test evidence may enter the tested system.
- After inspecting a locked failure to tune the system, move that family to development and create fresh independently reviewed locked cases in a new version. Never quietly rewrite expected answers after seeing outputs.
- No model-generated grading alone establishes a reference answer. Domain review checks each claim against the pinned source; uncertain labels remain pending and cannot count toward a release-quality claim.

## How to run each kind

| Kind | Input and evidence | What to observe |
| --- | --- | --- |
| Technical | Run prompt through complete A/retrieval/B/C path in a fresh session | Correct need, retrieved clause/conditions, final claims, bound citations, latency and calls |
| Behavior | Replay history or execute explicit fixture steps, then submit prompt | Clarification/state transitions, exact-history recovery, scope handling, stopping and publication |
| Reviewer | Supply candidate text plus source, original task and valid backend bindings; C gets no gold labels | Blocking falsehoods, acceptance of supported content, prior-candidate regression check |

For reviewer trials, construct full valid production-shaped candidate/citation/binding records; the fixture text is not itself a complete `COutput` or candidate contract. Keep expected judgments grader-side. For C04 use the prior candidate from the fixture and a nonzero correction round. For isolated B trials supply the verified original clauses directly (oracle-context condition). Report those separately from end-to-end retrieval trials: manually supplying missing evidence must not hide parser failures.

For B02, load the exact stated conversation before the final prompt; retrieve current source support independently of the prior assistant message. For B08 preserve all exact history messages while forcing older content out of the recent window. Source-injection tests must use an isolated fixture build; never mutate the production PDFs or their hashes. Fault cases use controlled injection, never real secrets or uncontrolled outages.

## Scoring contract

Each case lists atomic `expected` criteria and `forbidden` outcomes. Assign each expected criterion 1 (met), 0.5 (partially met), or 0 (missing/wrong), with an output/source reference and brief rationale. Two reviewers should independently assess a representative calibration sample before trusting an automated grader; disagreements go to a domain reviewer. Until that happens, report grading as provisional.

Record these separately; do not collapse them into one flattering percentage:

- **Answer completeness:** met-point sum / number of expected points, per technical case. Correctness requires no contradictory technical claims; extra unsupported assertions are errors even if expected points are present.
- **Source support:** supported substantive claims / all substantive claims; inspect inline and end citations against the exact version and clause. A fabricated citation or wrong release is a critical failure.
- **Retrieval hit@5:** whether at least one of the top five passages supports a required source clause; for multi-source questions also report required-clause recall@5. Merely matching a document number is not a hit. Required clauses are starting references, not a ban on other valid support.
- **Safety/control:** all relevant state/budget/publication checks must pass. Safe abstention earns a safety pass, but scores zero for unavailable technical-answer points; report abstention rate explicitly.
- **Reviewer:** false-acceptance rate on C01/C02/C04/C06 and false-objection rate on C03/C05. The six seeds are diagnostic; do not infer general reviewer reliability from them.
- **Efficiency:** wall time, active processing time, provider calls, retries, quota failures and token accounting method. Report UTF-8 budget bounds separately from actual provider-reported tokens. Never label byte counts measured tokens.

A trial is a strict pass only if every applicable expected criterion is met and no forbidden outcome occurs. Critical failures include fabricated evidence, silent release substitution, unreviewed answer publication, secret disclosure, lost cancel fencing or a budget reset. Any observed critical failure blocks a candidate configuration pending investigation. This is an engineering comparison gate; it does not approve proposed SRS numerical targets.

Use one smoke trial first, then three trials per selected case/configuration within an explicit finite quota/time budget. Report all trials (including failures/timeouts), denominators and unavailable runs. Distinguish provider/infrastructure errors from answer errors; do not silently discard either. Report averages and ranges for this small sample, not unsupported tail-latency claims or statistically significant provider rankings. Publish confidence intervals only with stated methods and sample counts. Preserve per-case paired outcomes when comparing configurations.

## Result record (future harness contract)

Each JSONL trial record must contain: suite version and SHA-256 of cases.json; case ID/split/trial index; UTC time; Git commit; corpus manifest/build/parser identity; A/B/C provider/model and prompt/config hashes; outcome/status; final text and citation/source IDs; safe tool/state event sequence; observed latency/calls/retries/token usage and accounting method; each criterion score/rationale; forbidden outcomes; grader identity/version; domain-review status and sanitized error code. No API keys, private conversations, raw authorization headers or hidden chain-of-thought. Save detailed results as CI artifacts or ignored local `data/evaluation/`; commit only a concise reviewed result summary.

Current result status: **not run against live providers**. No A/B/C provider assignment is selected by this suite. Existing deterministic runtime tests remain separate regression evidence.

## Validate and maintain

From repository root (Python 3.12):

```bash
python evaluation/validate.py
python evaluation/validate.py --raw-dir data/corpus/nr-l1-l2-rel18-2026-10-24/raw
```

The second command requires Poppler `pdftotext`. It checks all source-file SHA-256/size pins and cited-page anchors/clauses, with bounded per-page extraction. It does not judge semantic correctness or run the chatbot. The first command needs only Python's standard library and runs in ordinary CI without PDFs or API keys.

Changes to source versions, gold points, splits or grading require a suite-version update and PR review. Retain old suites through Git commits. Refresh source labels deliberately after a manifest change; do not auto-relabel. Track domain review in issue #4, provider comparisons in #5, evaluation acceptance in #6 and extraction gaps in #7.

## Natural-question protocol (0.2.0)

All 16 primary technical questions omit document, clause and table locators.
Each has one natural paraphrase, including English, Hinglish and selected typos.
14 also retain the former source-hinted wording as a diagnostic control.
These are **40 cases and 30 variants**, not 70 independent knowledge questions.
Run each wording in a fresh session with identical declared corpus configuration.
The application default is the pinned NR Release 18 collection; it may state this
scope without demanding a TS number. Clarify only when missing intent would
materially change the answer. B13/B18 test unnecessary clarification; B15 tests
real ambiguity. B14 tests false-premise correction; B16/B17 test absent/stale evidence.
C05 balances reviewer rejection tests with another valid answer; C06 tests a
plausible answer with an unrelated citation.

`inputs.user_input` projects only prompt/history. Never send the full case JSON,
expected/forbidden points, sources, family, split or fixture instructions to A/B.
Reviewer candidates and supplied evidence need a separate production-contract
adapter; this helper does not execute fixtures. The entire evaluation directory
must be excluded from the production retrieval index. Expected sources are
used by graders after retrieval, never as automatic search filters. Oracle-context
B tests and source-hinted runs are diagnostic conditions with separate scores.

Report primary natural results first, paraphrase robustness second, and the paired
hinted-minus-natural result separately. Average variants within each base case
before aggregate reporting; never let extra wordings inflate sample size. Report
counts by split, kind, language/style, family and evidence availability. Include
unnecessary-clarification rate on answerable questions and clarification success
on ambiguous questions. Do not merge safe abstentions with successful answers.
For reviewer results show the confusion matrix and raw counts, not only accuracy.

This revision changes locked question wording before any reported live benchmark;
the locked set remains publicly exposed and reserved by process only. Gold points
and source pins from 0.1.0 are retained, not independently re-certified. Added
source-based cases inherit that candidate status; ambiguous or disputed labels
must be quarantined from release-quality scores until domain review resolves them.
Record reviewer identity, review date, per-criterion decision and source rationale
in the result artifact. Log every label correction with old/new suite hashes.

Before live comparison, pre-register selected cases/variants, configurations,
three trial indices, maximum calls, per-call/run timeouts and total budget. Stop
at the first exhausted budget; retain incomplete runs in the report. Randomize
configuration order with a recorded seed, blind provider identity during grading,
and calibrate graders on a fixed sample including correct, incorrect and abstained
answers. Freeze selection before locked validation. These data and offline guards
are ready; a production-shaped live runner, domain approval and actual model
results remain pending. No company-internal benchmark equivalence is claimed.


## Provider readiness gate

[Live readiness instructions](READINESS.md) define bounded metadata checks and an optional free-only A clarification smoke across Gemini/Groq/Mistral. This is separate from the full trial harness and technical-quality benchmark, which remain pending.
