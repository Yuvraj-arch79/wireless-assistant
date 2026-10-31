# Prototype verification and remaining work

**Version:** development prototype 0.1.0. **Recorded:** 31 October 2026.

The agreed product scope is unchanged. This checkpoint implements the local UI/backend, durable A–B–C controller, source ingestion and hybrid retrieval adapter. It is not acceptance of all 94 requirements or a production-ready release. The [design coverage matrix](../design/verification.md) remains the requirement-by-requirement reference.

## Executed evidence

| Check | Result / boundary |
| --- | --- |
| Offline Python suite | 63 tests passed locally, including 22 acquisition tests and 41 runtime tests; 9 unittest subtests also passed. Browser test is separate and opt-in. |
| Design assertions | Run `python docs/design/validate_design.py`; these remain structural/document/database checks, separate from runtime tests. |
| Real source ingestion | All 12 manifest-pinned PDFs verified and parsed with pdfplumber 0.11.10 / `pdfplumber-clause-v2`; 6,921 passages, 2,710 marked excluded/unreadable, 3 oversized-table warnings. Front matter is included in the exclusion count. |
| Real lexical retrieval probes | RLC functions, PDCP compression and MAC prioritization returned relevant clauses. The resource-block definition probe did not return the desired definition in the top 3. These four exploratory probes are not a held-out benchmark. |
| Real provider generation/embedding | **Not run:** no private API credentials supplied. Successful fixture calls do not prove live schema compliance, latency, quotas, hybrid ranking quality or answer correctness. |
| Browser UI | Chromium fixture flow passed in [GitHub CI](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/41159295859/job/124413032279): send/review, source inspection, feedback, rename/reopen, idle clarification, cancel and deletion. Local browser download was unavailable. |
| Platforms | Linux local execution; Windows/Linux matrix in CI is required before merge. No macOS/mobile acceptance claim. The first Windows run exposed lock-file reads raising raw PermissionError; the lock now handles this safely and is retested in CI. |

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
| Models | Separate A/B/C calls to configurable Gemini models; one provider adapter; strict backend validation and one global format repair | Live model contract/quality tests; same-model correlated mistakes remain possible |
| Limits | 180 s active budget; 25 s provider, 5 s tool; 12 provider calls including query embeddings, 2 retries, 1 repair, 4 searches, 4 history operations, 24 tools, 96 controller steps; 2 active runs | Tune with actual provider and corpus measurements |
| Context accounting | Conservative UTF-8 byte bounds for inputs: 24,000 per role, 250,000 charged per run; provider output cap 2,000 tokens; recent history 1,500 bytes; compact excluded map 800 bytes | These are development accounting ceilings, not exact provider-token measurements. Example LLD numbers are not runtime configuration. |
| History | Last four whole turns that fit; mandatory original question/critical replies; exact searchable originals and paged fetch | No model-generated summary. Large mandatory context stops clearly instead of dropping details. |
| Recovery | One OS-locked application process, per-run epochs, independent supervisor; active runs become INTERRUPTED on restart, waiting stays idle | Multi-process leases/distributed hosting are not implemented or intended deployment |
| UI/events | Safe plain-text rendering of B's exact Markdown, clickable source buttons, bounded status polling; SSE API also available | Rich Markdown/math display and SSE-driven UI remain refinements; current text is never inserted as HTML |
| Privacy | Local state, explicit chat deletion, backup command, server-only API key, no raw provider response/access logs | Provider data terms and retention sign-off; deletion does not erase external backups/provider copies |

Global capacity is two run workers; each issues at most one provider operation at a time. Optional collection stops early enough to reserve B/C calls; if insufficient validated context or budget remains, the run ends clearly. Clarification waiting has no autonomous activity. A user can explicitly start a new bounded retry; the system cannot keep doing this automatically.

Schema v1 is the reference design schema plus runtime-state/FTS/vector/report tables. Stored operations identify requests and outcomes; no private model reasoning is stored. Code ownership maps directly to modules in `wireless_assistant/`: `app` (HTTP/security), `engine` (routing), `store` (transactions/history), `contracts`/`validation` (boundaries), `bounded`/`provider`/`local_tools` (workers), `corpus` (evidence), `static` (UI).

## Next acceptance work

1. Configure a billing-disabled API project, finish the real hybrid build and run representative questions through the whole UI.
2. Define a domain-reviewed question/expected-clause set covering all 12 documents, ambiguity, unavailable releases, equations and table conditions. Record retrieval, citation support, answer correctness, regression, latency and quota outcomes.
3. Fix measured parser/retrieval/model failures without changing the agreed scope. Do not silently mark excluded content as readable to increase coverage.
4. Review privacy/retention and proposed SRS gates, then update issues #4–#7 and approve a pilot separately from this prototype checkpoint.
