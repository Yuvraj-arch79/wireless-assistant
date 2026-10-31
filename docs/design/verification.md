# Design review, coverage and verification

**Revision:** DESIGN-LLD-001 / 0.1, 23 October 2026.

**Scope:** Design artifacts and reference database constraints. Application acceptance is pending.

**Current progress, 31 October 2026:** A first implementation and offline runtime regression suite now exist; see [prototype verification](../implementation/verification.md) for results, gaps and reproduction. Full application acceptance remains open.

**Historical progress, 24 October 2026:** [PR #9](https://github.com/Yuvraj-arch79/wireless-assistant/pull/9) implemented source acquisition for the [12 pinned PDFs](../../corpus/README.md). Live download/verification and 22 offline acquisition tests passed. The review basis and executed-check counts below record the 23 October design snapshot; they are historical evidence, not current inventory/link counts. Application acceptance remains pending.

## Review basis

- Live repository main at `3109b11170784a71ac3d21131700277b5ffdee93`, its 18 files, requirements and issue records #4–#7. The snapshot contains planning documents and an SRS renderer, not an application.
- SRS 0.9.1: 94 requirement IDs, 30 acceptance scenarios, D01–D11; product brief and existing architecture.
- Owner's product/design review through 23 October 2026: C-to-B feedback, original-query preservation, UI/history decisions, repeat necessary clarification, finite processing and failure recovery. The resulting clarification decision is recorded in [the decision register](../decisions.md); implementation details are in the LLD and handoff.

This is a reconciliation of the available sources, not a claim that every possible future defect is known. Historical assistant suggestions do not override later user decisions. No model, corpus, quality target or stack choice is represented as benchmarked or approved merely because an earlier chat called it final.

## Changes and their reasons

| Change | Resulting behavior | LLD section |
| --- | --- | --- |
| Removed one-clarification limit and forced proceed | Ask a precise necessary question; same-gap no-progress becomes an idle information-needed state | 3.2 |
| Separated waiting from active execution | No worker, provider call, database transaction or spinner while waiting for the user | 3.1–3.2 |
| Preserved counters through clarification and re-entry | No hidden budget reset within a run; explicit retry creates a linked bounded attempt | 3–4 |
| Added total and per-operation deadlines | A single hung call, retry delay or tool cannot rely solely on correction count to terminate | 4 |
| Included nested/SDK retries, tokens and parallel reservations | Hidden calls, embedding, repairs and query batches cannot bypass accounting | 4.1 |
| Added bounded global capacity and controller steps | Many sessions or an unexpected internal transition cannot create unlimited work | 4.1 |
| Specified closing reserve | Attempt a supported final B candidate plus C review within remaining draft slots | 4.2 |
| Corrected no-progress and empty-search logic | A first empty search may use a useful alternative; equivalent repeated failures stop | 4.2, 6 |
| Made session claim and reply consumption atomic | Double-click/two-tab submissions and duplicate replies do not start two runs | 3.1 |
| Added cancellation fencing and one terminal commit | Late workers cannot publish, clear another run's lock, or resurrect deleted data | 3.1, 7.5 |
| Added crash recovery and stream reconciliation | Interrupted work is labeled honestly; refresh reconnects to saved status | 3.3, 9 |
| Reordered final persistence and display | Save exact checked answer and event before delivery; replay is deduplicated | 7.5, 9 |
| Removed previous-turn size contradiction | Recent context stays bounded; oversized original material remains fetchable | 5 |
| Covered every excluded history message | Actual selected/excluded set drives the compact map; complete local history remains searchable | 5 |
| Restored original query/replies and regression inputs | B/C cannot rely only on A's summary; revisions retain reasons and prior findings | 7 |
| Completed immutable approval binding | Exact candidate, need, context, evidence and corpus/configuration versions remain traceable | 6–8 |
| Rejected contradictory judge decisions | Accepted plus blocking findings, malformed coverage or stale IDs cannot be treated as a pass | 7.4–7.5 |
| Restored full UI/backend API coverage | Listing, opening, renaming, replies, status/reconnect, evidence and feedback have explicit routes | 9 |
| Completed ingestion fingerprint and snapshot retention | Controlled activation/rollback; active runs and saved citations keep exact evidence | 6 |
| Corrected security claims and deletion scope | XML is a delimiter; backend permissions, origins, rendering, file boundaries and retention enforce controls | 11 |
| Corrected requirement references | Loopback uses SEC-07; source details UX-03, inspector UX-04, hidden drafts UX-06, keyboard UX-07 | 10–11 |
| Removed unsupported completion claims | Design review, implementation, benchmark and acceptance remain distinct | 1, 12 |
| Completed developer handoff | Connection-by-connection data shapes, API payloads, transaction ownership and implementation order are explicit | [Implementation guide](implementation-guide.md) |

## Requirement coverage

Each existing requirement appears exactly once. Section references point into [system-design.md](system-design.md); scenario IDs retain the SRS mapping. Coverage means the design addresses the requirement, not that the application has passed it.

| Requirement | Existing requirement title | Design section | Original acceptance scenarios |
| --- | --- | --- | --- |
| DOM-01 | Keep the original request | 7.1 | T01 |
| DOM-02 | Use domain clues carefully | 1–3, 7 | T02 |
| DOM-03 | Explain clear scope limits | 1–3, 7 | T03 |
| DOM-04 | Ask when the answer depends on it | 1–3, 7 | T01, T02, T04 |
| DOM-05 | Use information already available | 1–3, 7 | T01, T02, T04 |
| DOM-06 | Pause and resume clarification | 3.1–3.2 | T01, T02, T04 |
| DOM-07 | Avoid unnecessary questioning | 1–3, 7 | T01, T02, T04 |
| DOM-08 | Separate scope from coverage | 1–3, 7 | T03 |
| CTX-01 | Store original conversation | 3, 5, 7–8 | T02, T05, T22 |
| CTX-02 | Select recent context | 5 | T02, T05, T22 |
| CTX-03 | Retrieve older details on demand | 5 | T02, T05, T22 |
| CTX-04 | Use summaries as aids | 5 | T02, T05, T22 |
| CTX-05 | Avoid automatic extra LLM calls | 3, 5, 7–8 | T02, T05, T22 |
| CTX-06 | Record the current need | 3, 5, 7–8 | T01, T04, T05, T11 |
| CTX-07 | Respect user corrections | 3, 5, 7–8 | T01, T04, T05, T11 |
| CTX-08 | Keep format flexible | 3, 5, 7–8 | T01, T04, T05, T11 |
| RAG-01 | Declare coverage | 6, 8, 11 | T03, T06, T08, T20 |
| RAG-02 | Prepare documents before questions | 6, 8, 11 | T03, T06, T08, T20 |
| RAG-03 | Preserve source structure | 6, 8, 11 | T03, T06, T08, T20 |
| RAG-04 | Split by meaning | 6, 8, 11 | T03, T06, T08, T20 |
| RAG-05 | Store text with each vector | 6, 8, 11 | T03, T06, T08, T20 |
| RAG-06 | Keep embeddings compatible | 6 | T07 |
| RAG-07 | Avoid repeated ingestion cost | 6 | T07 |
| RAG-08 | Publish a valid collection atomically | 6 | T07 |
| RET-01 | Separate request from execution | 4, 6–7 | T08, T29 |
| RET-02 | Respect version scope | 4, 6–7 | T03, T09, T12 |
| RET-03 | Pass original evidence | 4, 6–7 | T08, T29 |
| RET-04 | Support exact and semantic matches | 4, 6–7 | T08, T29 |
| RET-05 | Expand necessary context | 4, 6–7 | T06, T10, T17 |
| RET-06 | Tune retrieval with evidence | 4, 6–7 | T08, T29 |
| RET-07 | Handle missing and conflicting evidence | 4, 6–7 | T03, T09, T12 |
| RET-08 | Bound repeat searches | 4.1–4.2, 6 | T06, T10, T17 |
| ANS-01 | Answer the actual need | 2, 4, 7 | T01, T09, T11 |
| ANS-02 | Ground technical claims | 2, 4, 7 | T01, T09, T11 |
| ANS-03 | Preserve conditions and exceptions | 2, 4, 7 | T01, T09, T11 |
| ANS-04 | Request precise missing data | 2, 4, 7 | T04, T10, T12, T15 |
| ANS-05 | Write limitations with the answer | 2, 4, 7 | T04, T10, T12, T15 |
| ANS-06 | Revise only justified parts | 7.3–7.4 | T14, T15, T18, T20 |
| ANS-07 | Use simple, suitable language | 2, 4, 7 | T01, T09, T11 |
| ANS-08 | Be the only technical writer | 7.5 | T14, T15, T18, T20 |
| REV-01 | Review the exact draft | 4, 7, 12 | T13, T14, T18 |
| REV-02 | Return findings, not a new answer | 4, 7, 12 | T13, T14, T18 |
| REV-03 | Separate issue types | 4, 7, 12 | T13, T14, T18 |
| REV-04 | Make objections actionable | 4, 7, 12 | T13, T14, T18 |
| REV-05 | Check support and coverage | 4, 7, 12 | T13, T14, T18 |
| REV-06 | Check for regression | 7.4 | T12, T15, T29 |
| REV-07 | Allow an honest partial result | 4, 7, 12 | T12, T15, T29 |
| REV-08 | Treat judge quality as measurable | 12 | T12, T15, T29 |
| ORC-01 | Own the workflow in code | 3–4, 7–9 | T10, T14, T15, T16, T17, T23 |
| ORC-02 | Enforce two correction rounds | 4.2 | T10, T14, T15, T16, T17, T23 |
| ORC-03 | Use shared resource limits | 4.1 | T10, T14, T15, T16, T17, T23 |
| ORC-04 | Reserve a closing path | 4.2 | T10, T14, T15, T16, T17, T23 |
| ORC-05 | Stop when progress stops | 4.2 | T10, T14, T15, T16, T17, T23 |
| ORC-06 | Bind approval to the answer | 7.5 | T18, T19, T22 |
| ORC-07 | Never release a failed draft by default | 3–4, 7–9 | T18, T19, T22 |
| ORC-08 | Make completion consistent | 3.1, 7.5 | T18, T19, T22 |
| UX-01 | Keep the chat readable | 9–10 | T19, T21, T22 |
| UX-02 | Match citations to claims | 9–10 | T12, T20 |
| UX-03 | Show meaningful source details | 9–10 | T12, T20 |
| UX-04 | Allow evidence inspection | 9–10 | T12, T20 |
| UX-05 | Show limitations where they matter | 9–10 | T12, T20 |
| UX-06 | Hide internal drafts | 7.5, 10 | T19, T21, T22 |
| UX-07 | Support simple interaction | 10 | T19, T21, T22 |
| UX-08 | Handle retry and cancellation | 3, 9–10 | T19, T21, T22 |
| API-01 | Run locally with clear prerequisites | 4, 7, 9, 11–12 | T24 |
| API-02 | Keep API access on the backend | 4, 7, 9, 11–12 | T25 |
| API-03 | Validate role contracts | 4, 7, 9, 11–12 | T23 |
| API-04 | Use configurable role providers | 4, 7, 9, 11–12 | T24 |
| API-05 | Stay within free-service constraints | 4, 7, 9, 11–12 | T23 |
| API-06 | Handle cloud failures explicitly | 4, 7, 9, 11–12 | T23 |
| API-07 | Document supported boundaries | 4, 7, 9, 11–12 | T24 |
| SEC-01 | Protect secrets | 11 | T25 |
| SEC-02 | Explain cloud data use | 10–11 | T25 |
| SEC-03 | Send only necessary context | 5–6, 8–9, 11 | T25 |
| SEC-04 | Provide local history deletion | 5–6, 8–9, 11 | T26 |
| SEC-05 | Declare retention and backup behavior | 5–6, 8–9, 11 | T26 |
| SEC-06 | Treat retrieved content as untrusted | 5–6, 8–9, 11 | T27 |
| SEC-07 | Restrict local access | 11 | T27 |
| SEC-08 | Control document handling | 5–6, 8–9, 11 | T27 |
| OPS-01 | Keep work bounded | 3–4, 8–12 | T17, T21, T28 |
| OPS-02 | Acknowledge and show progress | 3–4, 8–12 | T17, T21, T28 |
| OPS-03 | Measure response time honestly | 3–4, 8–12 | T17, T21, T28 |
| OPS-04 | Recover consistent state | 3.3 | T22 |
| OPS-05 | Account for quotas and usage | 3–4, 8–12 | T23, T28 |
| OPS-06 | Cache only compatible results | 3–4, 8–12 | T23, T28 |
| OPS-07 | Avoid request races | 3.1 | T22 |
| OPS-08 | Publish measured limits | 3–4, 8–12 | T23, T28 |
| MNT-01 | Version the behavior | 8–12 | T28 |
| MNT-02 | Keep useful diagnostic records | 8–12 | T28 |
| MNT-03 | Collect simple quality feedback | 9–10 | T30 |
| MNT-04 | Separate testing from tuning | 8–12 | T24, T29 |
| MNT-05 | Review and roll back changes | 8–12 | T24, T29 |
| MNT-06 | Provide reproducible setup | 8–12 | T24, T29 |
| MNT-07 | Keep specifications in sync | 12 | T30 |

## Additional fault scenarios for implementation

This is the **design-stage scenario register**. The prototype verification record links executed regression coverage; full scenario acceptance is not inferred from those tests. Record the concrete versions, trace, expected result, observed result and reviewer. The schema checks in the next section cover only a subset of the database mechanics.

| Case | Injected condition | Required result |
| --- | --- | --- |
| F01 | Two unclear clarification replies, then a useful detail | No repeated busy loop; specific waiting message; later detail handled once |
| F02 | Same clarification reply twice or a reply to an old question | One consumption; stale reply rejected with current status |
| F03 | Provider never responds, including during final C review | Deadline ends active work; no unchecked answer; chat usable after reconciliation |
| F04 | Repeated rate limit, long Retry-After, malformed JSON and SDK retry | Shared counters/deadline bound all attempts; distinct recorded stop reason |
| F05 | Parallel searches/embedding calls at the last available quota | Atomic reservations prevent overspend; no batch bypass |
| F06 | Stop races with completion; then a new question | One terminal result; late old worker cannot publish or unlock the new run |
| F07 | Two tabs/double-click submit the same or different question | Deduplicate same intent; block overlapping intent; at most one unfinished run |
| F08 | Restart during API call, waiting, and after final commit before delivery | Active becomes interrupted; waiting survives; committed result is replayed once in UI |
| F09 | SSE disconnect, stale cursor, refresh, and backend outage | Bounded reconnect; status reconciliation; no automatic duplicate generation or endless spinner |
| F10 | Database lock, disk full, corrupted database, or worker freeze | Bounded error/recovery; independent supervision; no false saved/completed claim |
| F11 | Previous turn exceeds recent budget; only two turns exist | Excluded messages remain indexed; exact original can be recovered; no silent context loss |
| F12 | Huge original query, evidence expansion, or prior draft exceeds model context | Preserve essential material or explain/narrow; no hidden truncation or paid fallback |
| F13 | First query empty, alternative term succeeds; repeated identical query empty | Useful bounded alternative allowed; useless equivalent repetition blocked |
| F14 | Need changes or corpus activates while an answer is being reviewed | Stale approval rejected; pinned build remains consistent; latest correction respected |
| F15 | C approves wrong hash/evidence, unknown IDs or contradictory status | Reject/repair within budget; no release from malformed record |
| F16 | C misses an error, wrongly blocks a correct draft, or B loses a correct example | Human-reviewed controls measure judge failure and regression; no accuracy guarantee inferred |
| F17 | Final allowed candidate fails; no closing reserve remains | No fourth draft, unreviewed cleanup or rejected-draft fallback |
| F18 | Cyclic cross-reference graph, malformed table or incompatible embeddings | Bounded expansion; unreadable evidence excluded; incompatible build rejected |
| F19 | Ingestion crashes before activation or old build is garbage-collected | Previous active build remains usable; retained citation evidence still opens |
| F20 | Delete chat while API callback/retry/history lookup is in flight | Tombstone/fence blocks reads and resurrection; linked/derived data purged |
| F21 | Prompt injection, malicious Markdown, remote origin, unsafe path | Roles/tools/release gate preserved; safe rendering and local-access rejection |
| F22 | Many simultaneous chats and exhausted free allowance | Finite global capacity; clear busy/quota outcome; no unbounded queue or billing |
| F23 | Reopen/rename/search chats; keyboard-only use; feedback submission | Complete visible lifecycle; report linked to exact answer without automatic model rerun |
| F24 | New provider/model/prompt/parser/configuration version | Targeted held-out evaluation, compatible caches and rollback; no silent mid-run switch |

## Executed checks

Run from the repository root:

```bash
python docs/design/validate_design.py
```

The standard-library validator checks finite example values and closing reserves; the 94-ID/30-scenario mapping; SQLite DDL execution; foreign-key ownership; one unfinished run per session; concurrent claims from two database connections; immutable need/context/evidence/candidate/review records; invalid review bindings; contradictory acceptance; conditional cancel/late completion; idempotency uniqueness; and cascade deletion without harming a second session.

**Recorded result, 23 October 2026:** 96 document/configuration/database assertions passed using Python 3.12.14 and SQLite 3.53.1. This includes the dedicated waiting-to-reply transition, one-time clarification consumption, rejection of terminal-run resurrection, preservation of original messages, handoff reference/link checks and JSON example syntax. The 96 assertions include individual configuration-value checks; they are not 96 application scenarios.

All 94 SRS requirements have one mapping row, all 30 original acceptance scenario IDs are retained, 67 local documentation file links resolve, and the prepared diff has no whitespace errors. The product brief, SRS Markdown and SRS PDF match the retrieved upstream bytes.

The test database uses synthetic records, including deliberately nontechnical placeholder JSON. Passing these tests proves only the tested structural constraints and transaction predicates. It does not validate real JSON role outputs, model accuracy, a provider timeout, UI recovery, full security, source parsing, semantic coverage, or deployed behavior. This historical design-check result does not mark F01–F24 or SRS application scenarios accepted. See the current prototype verification record for implemented regression coverage.

Document checks also compare the SRS source/PDF and product brief to the retrieved upstream blobs, check relative links and inspect the final diff. The original SRS and its matching PDF are unchanged.

## Remaining work

- Review domain coverage, runtime release defaults and supporting examples for the pinned development source set (#4); acquisition and byte identity are already verified.
- Benchmark model APIs, exact/semantic retrieval, parser/storage/framework and capacity (#5).
- Approve numeric operating values, supported platforms/languages, retention/provider disclosure and human evaluation gates (#6).
- Implement the specified behavior, then execute acceptance and failure scenarios with evidence. A schema validator is not a replacement for those tests.
- Keep the published design and implementation handoff aligned with subsequent PRs. Merging this design does not close the open implementation, benchmarking or application-acceptance work.
