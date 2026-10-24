# Changelog

This log tracks project documentation and design changes. SRS versions are document versions, not application releases.

## 2026-10-24 — Repository status consistency

- Align product brief, architecture, LLD, implementation handoff, verification, overview and contribution guidance with completed source acquisition and pending chat-runtime work.
- Distinguish the dated SRS/design verification snapshots from the live decision register; preserve the matched SRS/PDF and historical test results.
- Add a cross-document and issue/milestone status check to contribution/PR guidance.

## 2026-10-24 — Reproducible source acquisition

- Lock all 12 owner-listed initial PHY/Layer-2 specifications to exact Release 18 official ETSI PDFs, including SHA-256, byte size, page count and original 3GPP archive references.
- Add a standard-library download/verify tool with bounded attempts/deadlines, checksum enforcement, atomic file promotion, full-collection receipts and offline failure tests.
- Add a clone/setup/update/recovery guide and repository CI checks. Keep original PDFs and all generated data in the existing ignored local data directory.
- Record the source baseline as a development choice; leave domain/default-release review, parsing/indexing, model integration and application acceptance pending.

## 2026-10-23 — Detailed design robustness review

- Add DESIGN-LLD-001 covering the full product flow, finite processing, repeat clarification without forced guessing, concurrency, cancellation, recovery, contracts and exact reviewed-answer delivery.
- Correct history selection/coverage, bounded alternative retrieval, source-build pinning, immutable evidence versions, complete UI APIs, security wording and requirement references.
- Add a reference SQL data model, explicitly provisional development limits, a standard-library design validator and mapping of all 94 requirements to the existing acceptance scenarios.
- Add an implementation handoff with component connections, shared record types, role/tool action shapes, public API payloads, transaction responsibilities and dependency-ordered implementation gates.
- Add 24 implementation failure scenarios; retain pending status for application, provider, accuracy and security tests.
- Align the overview, architecture, roadmap and decision register. Preserve the product brief and SRS 0.9.1 source/PDF.
- Keep source/model/stack choices and baseline approval open; no runnable application or production-readiness claim is introduced.

## 2026-10-13 — Repository organization

- Publish the completed product brief and SRS package in main through their existing PRs.
- Preserve the user-edited five-point problem statement.
- Replace the brief's broad multi-model answer-synthesis wording with A collects, B writes and C judges.
- Add a documentation guide, architecture summary, decision register, roadmap and contribution guidance.
- Add issue and PR templates and clear local-data ignore rules.
- Track pending source, technology and baseline decisions in issues #4–#6; prepare evidence implementation in #7.
- Keep M1 open and SRS v0.9.1 in review-draft status.

## 2026-10-13 — SRS v0.9.1

- Route C's findings to B first.
- Call A during correction only for specific missing information requested by B.
- Align the PDF diagram, requirements, examples and acceptance scenarios.
- Count every feedback round, including an unchanged B draft, toward the two-round limit.

## 2026-10-12 — SRS v0.9

- Add a 36-page specification, editable source and reproducible PDF renderer.
- Define 94 requirements, 30 acceptance scenarios and traceability.
- Distinguish confirmed behavior, proposed implementation details and open decisions.
