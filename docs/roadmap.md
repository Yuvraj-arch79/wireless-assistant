# Delivery roadmap

**Current stage:** Development prototype v0.1.0 implements M2–M4 paths. M1 approval and M2–M6 acceptance gates remain open; live API and domain evaluation come next.
**Planning reference:** [SRS v0.9.1](requirements/wireless-assistant-srs.md)

## What is done

- The five user problems, intended users, goals, scope and assumptions are documented.
- The SRS includes 94 identified requirements, 30 acceptance scenarios and a complete requirement mapping.
- Initial A/B/C responsibilities, backend control, correction paths and stopping rules are documented.
- A detailed LLD, implementation handoff, reference data schema, provisional limits and complete requirement coverage are documented, including clarification, concurrency, timeout and recovery behavior.
- The PDF and editable source are published together.
- The initial 12 PHY/Layer-2 source PDFs have a [version/hash lock and download/verification tool](../corpus/README.md); the files stay local and outside Git.

The first runnable prototype now covers ingestion, retrieval adapters, local chat and bounded A–B–C control. [Executed tests and limitations](implementation/verification.md) are recorded separately from full product acceptance. Real provider benchmarks and real hybrid retrieval quality remain unverified.

## What must happen next

| Order | Work | Result needed |
| --- | --- | --- |
| 1 | [Review source scope — #4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) | Inventory/version lock exists; review default-release policy, missing dependencies and sample evidence before indexing |
| 2 | [Select technology — #5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5) | Benchmarked API, retrieval and local application choices |
| 3 | [Approve baseline — #6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) | Reviewed requirements, operating decisions and evaluation plan |
| 4 | [Build evidence foundation — #7](https://github.com/Yuvraj-arch79/wireless-assistant/issues/7) | Implementation exists; evaluate real hybrid retrieval and repair measured parser gaps |

The first two decision tasks can inform each other. Development defaults are selected in the decision register. The owner authorized a working prototype followed by measured iteration; remaining quality decisions gate pilot acceptance, not coding.

Review the [LLD and verification record](design/verification.md) alongside issue #6. Its document/database checks do not satisfy the runtime, quality or security acceptance gates in later stages.

## Stage exit conditions

| Stage | Deliverable | Exit condition |
| --- | --- | --- |
| M1 — Requirements and Initial Design | Product brief, SRS, architecture, decision record and backlog | Blocking choices resolved; proposed requirements reviewed; later decisions have an owner and a resolution plan |
| M2 — Evidence foundation | Corpus inventory, parser, index, retrieval and source viewer | Required passages and provenance verified; ingestion/retrieval checks recorded |
| M3 — Core chat | Need resolution, domain handling, clarification, history and B with citations | Core journeys work in an internal development build |
| M4 — Judge and control | C review, validators, finite budgets and exact-version delivery | Correct routing and bounded stopping verified, including regression cases |
| M5 — Pilot hardening | Privacy, diagnostics, failures and held-out evaluation | Measured quality, usability and latency reviewed with limitations |
| M6 — First release | Reproducible setup and release evidence | Declared scope, accepted requirements and test report approved |

M2–M6 describe delivery stages, not a claim that matching GitHub milestones already exist. M2–M4 now have a prototype implementation; their exit conditions are not automatically satisfied by merging code. M3 by itself is not the complete agreed product.

## Completion rules

[M1](https://github.com/Yuvraj-arch79/wireless-assistant/milestone/1) stays open while its blocking decisions remain unresolved. Closing the product-brief task does not close the milestone.

Do not add dates, staffing commitments, completed tests or accuracy claims without evidence. Update this roadmap when a stage outcome changes; use issues for the detailed work and recorded results.

## Tracking metadata correction

The existing M1 milestone description still contains the superseded phrase “multi-model answer synthesis.” Its intended replacement is “A collects context, B alone writes/revises, C reviews, and backend code controls delivery, with inline and end references.” The live description edit is pending authenticated milestone-edit access and is tracked in [issue #6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6). The role contracts in the SRS, architecture and LLD are authoritative; M1 remains open.
