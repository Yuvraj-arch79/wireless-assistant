# Prototype verification and remaining work

**Version:** development prototype 0.1.0 plus subsequent fixes on main. **Original checkpoint:** 31 October 2026. **Consistency update:** 1 November 2026. The original checkpoint tag remains unchanged.

The agreed product scope is unchanged. This checkpoint implements the local UI/backend, durable A–B–C controller, source ingestion and hybrid retrieval adapter. It is not acceptance of all 94 requirements or a production-ready release. The [design coverage matrix](../design/verification.md) remains the requirement-by-requirement reference.

## Executed evidence

| Check | Result / boundary |
| --- | --- |
| Offline Python suite (original checkpoint) | 63 tests passed locally, including 22 acquisition tests and 41 runtime tests; 9 unittest subtests also passed. Browser test is separate and opt-in. Later audit validation is recorded below rather than replacing historical results. |
| Evaluation-source validation (1 November 2026) | [32-case candidate suite](../../evaluation/README.md): all 12 PDF SHA-256/size pins and 13 cited pages/anchors checked locally with Poppler; 3 table/formula pages also inspected visually. Domain approval and live trials remain pending. |
| Design assertions | Run `python docs/design/validate_design.py`; these remain structural/document/database checks, separate from runtime tests. |
| Real source ingestion | All 12 manifest-pinned PDFs verified and parsed with pdfplumber 0.11.10 / `pdfplumber-clause-v2`; 6,921 passages, 2,710 marked excluded/unreadable, 3 oversized-table warnings. Front matter is included in the exclusion count. |
| Real lexical retrieval probes | RLC functions, PDCP compression and MAC prioritization returned relevant clauses. The resource-block definition probe did not return the desired definition in the top 3. These four exploratory probes are not a held-out benchmark. |
| Real provider generation/embedding | **Not run:** no private API credentials supplied. Successful fixture calls do not prove live schema compliance, latency, quotas, hybrid ranking quality or answer correctness. |
| Browser UI | Chromium fixture flow passed on merged PR #13 in [GitHub CI](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41196129554/job/124522546570): send/review, source inspection, feedback, sidebar rename/delete for current and unopened chats, reopen, idle clarification and cancel. Local browser download was unavailable. |
| Platforms | Linux local execution and Windows/Linux CI passed for merged PR #13 ([run](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41196129554)). The original Windows lock-file issue was fixed before that merge. No macOS/mobile acceptance claim. |

The source manifest SHA-256 for the ingestion observation was `a30b266b6e655278b8e874282c3e295ddf9284b626b68d25317264d4d1025391`. Build IDs are local identities, not portable source versions. Reproduction uses the manifest and parser/config versions. Original PDFs, indexes and user data are not committed.

## What the tests exercise

- Exact A → collection → A → B → C flow; accepted candidate is released unchanged with bound need/context/evidence hashes.
- C findings go to B; B's specific gap alone returns to A; maximum two corrections; no failed-draft fallback.
- Necessary repeated clarification goes idle, retains counters and original replies, resumes once, and survives restart. Fast replies cannot lose the new worker behind an old worker's cleanup.
- Same-session concurrent admission, duplicate command receipts, stale/cross-session references, cancel/delete while running, late results, explicit linked retry and interrupted restart.
- Killable hung operations, independent active-deadline supervisor, finite provider retry/repair budgets and bounded collection/history work.
- Whole-turn history selection under the cap; an excluded oversized turn is still fetchable by exact original reference. Latest-message/older-history pagination.
- Host/Origin/CSRF checks, strict JSON and role contracts, safe error messages, process locking, source inspection and feedback without generation.
- Synthetic PDF parsing, atomic build activation/rollback, missing-vector refusal, embedding shape validation and durable batch continuation.

These provide useful automated regression coverage, not proof against every race, prompt injection, parsing error or incorrect model judgment. Test transports are dependency-injected only in tests; production has no canned answer mode.

## Implementation choices and explicit gaps

| Area | Implemented choice | Acceptance still needed |
| --- | --- | --- |
| Application | Python 3.12, FastAPI, Uvicorn, local static JS/CSS, SQLite WAL/FTS5 | Measured hardware limits and usability review |
| Retrieval | BM25 + normalized 768-dimensional cosine vectors, reciprocal-rank fusion; bounded scan suitable for this small collection | Real embeddings, held-out retrieval evaluation and reranking decision |
| Parsing | Clause/page chunks, table cells/captions, neighbor and cross-reference expansion, excluded unreadable text | Equations, diagrams, spanning/complex tables, annex headings and cross-reference completeness need domain review; no OCR or vision repair |
| Models | Separate A/B/C calls to configurable Gemini models; one provider adapter; strict backend validation and one global format repair | Groq/Mistral adapters and per-role provider selection pending; compare the agreed Gemini/Groq/Mistral shortlist before assignment. Live contract/quality tests pending; same-model correlated mistakes remain possible |
| Limits | 180 s active budget; 25 s provider, 5 s tool; 12 provider calls including query embeddings, 2 retries, 1 repair, 4 searches, 4 history operations, 24 tools, 96 controller steps; 2 active runs | Tune with actual provider and corpus measurements |
| Context accounting | Conservative UTF-8 byte bounds for inputs: 24,000 per role, 250,000 charged per run; provider output cap 2,000 tokens; recent history 1,500 bytes; compact excluded map 800 bytes | These are development accounting ceilings, not exact provider-token measurements. Example LLD numbers are not runtime configuration. |
| History | Last four whole turns that fit; mandatory original question/critical replies; exact searchable originals and paged fetch | No model-generated summary. Large mandatory context stops clearly instead of dropping details. |
| Recovery | One OS-locked application process, per-run epochs, independent supervisor; active runs become INTERRUPTED on restart, waiting stays idle | Multi-process leases/distributed hosting are not implemented or intended deployment |
| UI/events | Safe plain-text rendering of B's exact Markdown, clickable source buttons, bounded status polling; SSE API also available | Rich Markdown/math display and SSE-driven UI remain refinements; current text is never inserted as HTML |
| Privacy | Local state, explicit chat deletion, backup command, server-only API key, no raw provider response/access logs | Provider data terms and retention sign-off; deletion does not erase external backups/provider copies |

Global capacity is two run workers; each issues at most one provider operation at a time. Optional collection stops early enough to reserve B/C calls; if insufficient validated context or budget remains, the run ends clearly. Clarification waiting has no autonomous activity. A user can explicitly start a new bounded retry; the system cannot keep doing this automatically.

Schema v1 is the reference design schema plus runtime-state/FTS/vector/report tables. Stored operations identify requests and outcomes; no private model reasoning is stored. Code ownership maps directly to modules in `wireless_assistant/`: `app` (HTTP/security), `engine` (routing), `store` (transactions/history), `contracts`/`validation` (boundaries), `bounded`/`provider`/`local_tools` (workers), `corpus` (evidence), `static` (UI).

## Next acceptance work

1. Add Groq/Mistral generation adapters and explicit per-role provider selection alongside Gemini, preserving shared deadlines/counters and no automatic paid fallback. Configure private free API access locally, finish the real hybrid build and run representative questions through the whole UI. Assignment of A/B/C follows comparison; providers may be reused across roles.
2. Define a domain-reviewed question/expected-clause set covering all 12 documents, ambiguity, unavailable releases, equations and table conditions. Record retrieval, citation support, answer correctness, regression, latency and quota outcomes.
3. Fix measured parser/retrieval/model failures without changing the agreed scope. Do not silently mark excluded content as readable to increase coverage.
4. Review privacy/retention and proposed SRS gates, then update issues #4–#7 and approve a pilot separately from this prototype checkpoint.

## Repository consistency audit — 1 November 2026

Baseline checked: main `aa54dcc7d99da7a12993ec3f0d5e0756496187dc` (PR #13). All 60 tracked local file blobs matched that GitHub tree before editing. Reviewed current README/contribution/product/architecture/LLD/handoff/setup/decision/roadmap text against runtime configuration, route/DTO declarations, controller transitions, CI and open issues #4–#7. Original dated SRS/PDF, corpus hashes and immutable checkpoint tags are retained; no requirement or corpus-version change is introduced.

| Finding | Correction |
| --- | --- |
| Some docs still said there was no runnable assistant, parsing was pending or the stack was unselected | Record implemented development choices consistently and keep acceptance work separate |
| Agreed Gemini/Groq/Mistral shortlist was absent | Record owner decision, unimplemented adapters and benchmark-dependent role assignment |
| Milestone correction was still marked blocked | Live M1 metadata already contains the agreed role wording; remove stale blocker and synchronize issue #6 |
| API handoff described different delete, health, history/outcome and retry responses; bootstrap route was missing | Align current wire contracts with code; disclose polling/SSE and offset-pagination limitations |
| Nullable types broke Markdown table columns | Escape literal pipes and add a structural check |
| Closing-mode collection could bypass essential ambiguity checking | Validate both paths to B against unresolved user-detail gaps (need and coverage) and uncertain intent; allow bounded repair to clarification, otherwise stop without B |
| Setup conflated corpus readiness with provider readiness and treated an existing tag as future work | Explain CLI versus HTTP readiness and record verified immutable tag commits |

Validation: **70 offline tests passed, 9 unittest subtests passed**; browser test is opt-in and skipped locally. Seven targeted regression cases cover closing-mode ambiguity and bounded rejection (six failed against the old controller; all seven pass with the fix). **98 structural/design assertions passed**, including all 94 requirement mappings, local file links, API route inventory and handoff table columns. Dependency consistency and `git diff --check` pass. PR CI must run Windows, Linux and the separate Chromium fixture before merge; its result is recorded on the PR.

This is a repository-consistency review with targeted runtime regression checks, not an exhaustive security/quality audit or a guarantee of no remaining defects. No live provider calls or new domain benchmark were run. The known extraction gaps, real embedding/answer evaluation, Groq/Mistral adapters and pilot sign-off remain open in issues #4–#7.
