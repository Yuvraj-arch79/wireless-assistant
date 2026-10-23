# Delivery roadmap

**Current stage:** M1 — Requirements and Initial Design.  
**Planning reference:** [SRS v0.9.1](requirements/wireless-assistant-srs.md)

## What is done

- The five user problems, intended users, goals, scope and assumptions are documented.
- The SRS includes 94 identified requirements, 30 acceptance scenarios and a complete requirement mapping.
- Initial A/B/C responsibilities, backend control, correction paths and stopping rules are documented.
- A detailed LLD, implementation handoff, reference data schema, provisional limits and complete requirement coverage are documented, including clarification, concurrency, timeout and recovery behavior.
- The PDF and editable source are published together.

This is completed documentation work. No runnable chatbot, indexed corpus, provider benchmark or product test pass is claimed.

## What must happen next

| Order | Work | Result needed |
| --- | --- | --- |
| 1 | [Select source scope — #4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) | Finite document inventory, release defaults and verified sample evidence |
| 2 | [Select technology — #5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5) | Benchmarked API, retrieval and local application choices |
| 3 | [Approve baseline — #6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) | Reviewed requirements, operating decisions and evaluation plan |
| 4 | [Build evidence foundation — #7](https://github.com/Yuvraj-arch79/wireless-assistant/issues/7) | Working, evaluated ingestion and retrieval on the selected corpus |

The first two decision tasks can inform each other. Start the evidence implementation only when its source and retrieval prerequisites are resolved.

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

M2–M6 are planned delivery stages, not a claim that matching GitHub milestones already exist. M3 by itself is not the complete agreed product.

## Completion rules

[M1](https://github.com/Yuvraj-arch79/wireless-assistant/milestone/1) stays open while its blocking decisions remain unresolved. Closing the product-brief task does not close the milestone.

Do not add dates, staffing commitments, completed tests or accuracy claims without evidence. Update this roadmap when a stage outcome changes; use issues for the detailed work and recorded results.
