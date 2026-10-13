# Decision register

**Reference:** SRS v0.9.1, “Settings and open decisions.”  
**Status date:** 13 October 2026

Requirements documentation is complete. Final acceptance of proposed requirements and several implementation settings remains open. Publishing the documents in main does not close these decisions.

## Confirmed design constraints

- Initial scope is 3GPP cellular information in a declared, prepared collection.
- A gathers context, B writes, C judges, and backend code controls and delivers.
- C's findings go to B; A is called during correction only for B's specific missing information.
- Relevant history and meaningful clarification help define the current user need.
- One initial draft plus at most two correction rounds is the starting policy.
- Limits are finite, limitations are visible, and failed or unchecked drafts are not automatically released.
- The intended deployment is localhost with configured free cloud APIs and no automatic paid fallback.

## Open settings and approval work

Owner labels below identify responsibilities; a named domain reviewer has not yet been assigned.

| SRS ID | Decision or review needed | Status | Responsible role | Required before | Work item |
| --- | --- | --- | --- | --- | --- |
| D01 | Exact specifications, releases and document versions | Open | Owner + domain reviewer | Corpus build | [#4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) |
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

## Record a decision

For each resolved choice, record:

1. The decision ID and question.
2. Alternatives considered and supporting evidence.
3. The selected option, constraints and trade-offs.
4. Who approved it and the date.
5. Affected requirement IDs, tests, configuration and document versions.
6. Conditions that would trigger another review.

Small decisions can be recorded here with a linked issue or PR. Add a separate decision document only when the supporting reasoning needs more space. Development defaults must remain labeled as defaults until accepted.
