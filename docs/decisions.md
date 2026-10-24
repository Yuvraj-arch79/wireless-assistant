# Decision register

**Reference:** SRS v0.9.1, “Settings and open decisions.”

**Status date:** 24 October 2026

Requirements documentation is complete. Final acceptance of proposed requirements and several implementation settings remains open. Publishing the documents in main does not close these decisions.

## Confirmed design constraints

- Initial scope is 3GPP cellular information in a declared, prepared collection.
- A gathers context, B writes, C judges, and backend code controls and delivers.
- C's findings go to B; A is called during correction only for B's specific missing information.
- Relevant history and meaningful clarification help define the current user need.
- One initial draft plus at most two correction rounds is the starting policy.
- Limits are finite, limitations are visible, and failed or unchecked drafts are not automatically released.
- The intended deployment is localhost with configured free cloud APIs and no automatic paid fallback.

## Clarification and finite-processing decision

**Owner:** Project owner, recorded from the 23 October 2026 discussion.

**Design:** [DESIGN-LLD-001](design/system-design.md), especially sections 3–4.

**Affected requirements:** DOM-04 to DOM-07, CTX-07, ORC-02 to ORC-08, OPS-01, OPS-04, OPS-07, UX-08.

**Verification:** T04, T16–T19, T22–T23 and the additional failure scenarios in [design verification](design/verification.md).

Ask a clear, specific clarification whenever an unresolved essential detail would change the answer. One earlier question is not a reason to guess. Check available context first. Asking pauses dependent processing and removes the busy spinner; only a user reply resumes work. Repeated confusion must explain the exact missing detail instead of repeating an unhelpful question.

All autonomous work remains bounded. A clarification reply, role re-entry, automatic retry or format repair does not reset the same run's counters. Human waiting is idle and excluded from active-processing time. Exhausted allowance stops with a clear reason. An explicit retry/continuation can create a linked new bounded attempt; the backend cannot automatically create endless new attempts.

This supersedes the supplied PDF draft's one-clarification cap and forced continuation. It makes the existing SRS clarification and finite-budget requirements concrete. The owner requested these safeguards; the implementation mechanisms in the LLD and numeric example values remain subject to technical review and testing. Revisit this decision only through explicit behavior review, not a provider default.

## Open settings and approval work

### Initial source-acquisition baseline

On 24 October 2026, the owner requested reproducible acquisition of the provided initial PHY/Layer-2 list with a small repository. [The source lock and setup guide](../corpus/README.md) now cover all 12 listed specifications. Release 18 is the recorded development baseline selected for this acquisition work; exact versions, official ETSI PDF URLs and verified byte hashes are pinned in one manifest. The rationale is a single Release with version-specific official PDFs and repeatable downloads; no claim of complete cross-reference coverage or domain acceptance is made. Source files and generated data stay outside Git.

This partially resolves D01 for development. D07's user-facing default-release/clarification policy and domain review remain open. Changing Release or coverage requires a reviewed inventory update; acquisition cannot silently select newer versions or another Release. This does not select a model, parser, embedding/index technology or application framework.

Owner labels below identify responsibilities; a named domain reviewer has not yet been assigned.

| SRS ID | Decision or review needed | Status | Responsible role | Required before | Work item |
| --- | --- | --- | --- | --- | --- |
| D01 | Exact specifications, releases and document versions | Development source lock recorded; domain/coverage review pending | Owner + domain reviewer | Corpus build | [#4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) |
| D02 | Providers/models for A, B and C | Open | Developer + owner | Model integration | [#5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5) |
| D03 | Embeddings, store, exact/semantic matching and reranking | Open | Developer | Indexing | [#5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5) |
| D04 | Record the agreed two-correction policy in baseline approval | Agreed policy; approval record pending | Owner | Baseline approval | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D05 | Shared call, search, token, time and closing-reserve values | Open | Developer + owner | End-to-end pilot | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D06 | Recent window, summary trigger, history search and retention | Open | Developer + owner | History integration | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D07 | Default release and when to clarify it | Open | Domain reviewer | Technical pilot | [#4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) |
| D08 | Initial languages, OS and browser support | Open | Owner | Usability pilot | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D09 | Quality gates, test set, reviewer and latency target | Proposed targets; approval pending | Owner + reviewer | Pilot acceptance | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D10 | Provider data use, retention, backups and diagnostic access | Open | Owner + developer | Real-user data | [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| D11 | Frameworks, local stores, parsing and hardware capacity | Open | Developer | Initial design completion | [#5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5) |

All proposed SRS requirements also require review in issue #6. The numerical quality targets are proposed gates, not measured results.

The LLD documents candidate control, data and recovery mechanisms. [limits.example.json](design/limits.example.json) supplies development examples for D05/D06/D11; these are not benchmarked or owner-approved numerical targets. The reference SQL design does not close the storage/framework choice in D11. Source acquisition now has the development lock above; no indexed corpus, model/provider or retrieval stack has been selected or evaluated.

## Record a decision

For each resolved choice, record:

1. The decision ID and question.
2. Alternatives considered and supporting evidence.
3. The selected option, constraints and trade-offs.
4. Who approved it and the date.
5. Affected requirement IDs, tests, configuration and document versions.
6. Conditions that would trigger another review.

Small decisions can be recorded here with a linked issue or PR. Add a separate decision document only when the supporting reasoning needs more space. Development defaults must remain labeled as defaults until accepted.
