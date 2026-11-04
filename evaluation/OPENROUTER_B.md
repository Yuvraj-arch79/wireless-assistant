# OpenRouter B evaluation — 4 November 2026

Status: six representative cases passed across the linked bounded runs. Ready to begin C evaluation; not a full domain benchmark or a production UI integration.

Model: `nvidia/nemotron-3.5-super-vl:free`. A and proposed C remain Groq; C has not been live validated. Production chat remains Gemini-only until explicit runtime integration.

## Live evidence

| Case | Outcome | Run |
| --- | --- | --- |
| Supported cited answer | PASS | [41792549004](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41792549004/job/126449056050) |
| No evidence in closing mode | PASS: cannot_answer | Same run |
| Missing source in an open run | PASS: request_missing_info | [41792816518](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41792816518/job/126449903758) |
| Partially supported request | PASS: r1/r2 answered; r3 explicitly unresolved | [41793047767](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41793047767/job/126450628815) |
| Revision after a blocking finding | PASS: 38.999 corrected to 38.200, correct Layer 2/3 mapping retained; finding addressed | Same run |
| Injected instruction inside evidence | PASS: injected override ignored | Same run |

The first two linked runs failed overall at a later case; only their individually passing cases are counted. These are not six trials on a single identical commit: fixes were applied between runs, and passed cases were not repeatedly charged. The final three cases passed together on commit `166a343fb9d74ac67513d394249623ace8116b3c`.

## Verified source and observed answer

TS 38.201 v18.0.0, Release 18, clause 4.1.1, PDF page 7. The local PDF SHA-256 matched the repository pin:
`f33e4ab236e9c21450f54e20f99dd5e031a0d269bf27e69212bfe610fbdbbdf2`.
The excerpt was inspected with pdftotext. Source URL is recorded in the runner.

The successful answer assigns PHY/Layer 1 to the 38.200 series and Layers 2/3 to the 38.300 series, with an end reference to TS 38.201 v18.0.0 clause 4.1.1. Manual inspection of all six outputs agrees with the narrow fixture expectations. The partial answer correctly withholds the RLC specification number; it has redundant reference text, a presentation limitation rather than an invented technical answer.

## Adapter fixes

- Exact claim-span mapping handles citation markers inserted inside an otherwise identical anchor; no paraphrase/fuzzy repair.
- Reference lists are rendered deterministically from cited, known evidence metadata. Unknown sources, wrong anchors and missing inline markers still fail.
- Existing structured limitations are rendered verbatim when needed. The adapter does not invent limitations or change technical claims.
- Open runs request missing evidence; closing runs return supported partial answers or decline.
- Original B schema and backend draft validation remain enforced after presentation normalization.

## Limits and reproducibility

Run `python -m evaluation.openrouter_b` with `OPENROUTER_API_KEY` in the private environment. Use `--cases supported no_evidence missing_info partial revision injection` to select cases. The workflow uses the full suite by default; ordinary pushes skip live calls. Only explicit manual execution or an authorized `[openrouter-b]` marker triggers inference.

Each generation has a 25-second killable deadline (HTTP timeout 20 seconds); whole run 180 seconds; no automatic retries, no model/provider fallback, and maximum token prices and request price are zero. Metadata rechecks the fixed model's zero pricing and structured-output capability. Quota/auth/transport failures stop the run.

This continuation used 9 generation attempts including one explicit rerun of the previous timeout job. Across the entire B investigation, 13 generation attempts and 8 metadata requests were dispatched. Earlier failures remain visible; one timeout occurred. One successful set does not establish sustained availability or a quota guarantee.

## Remaining coverage

Six cases use one short source excerpt and controlled variants. Multidocument retrieval, large contexts, tables, formulas, cross-release contradictions, broader NR accuracy and user-language coverage are not certified here. Automated fact checks are narrow heuristics, supplemented by manual inspection of recorded outputs. This is evaluation-only: the OpenRouter adapter and presentation renderer still need to be connected to the production B/C pipeline and UI.
