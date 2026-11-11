# Changelog

## 2026-11-11 — Mixed provider runtime and explicit live demo

- Connect pinned Groq A/C and free OpenRouter B to the existing controller; share tested wire contracts and preserve original backend validation.
- Add a separate single-excerpt demo database, explicit UI scope notice and Windows setup instructions; full hybrid corpus setup remains separate.
- Cap C output at 900 tokens, bind backend identities without model echo, and retain low reasoning after a no-reasoning trial missed a regression.
- Pace mixed-provider calls within cancelable run deadlines; quota failures stop without automatic retry or paid fallback.
- Prevent skipped workflows from evicting an authorized pending live test.
- Verify the live controller end to end in four generation calls, with local source retrieval and a persisted C-approved cited answer; correct A’s source-document versus topic-series filtering.

## 2026-11-10 — Bounded Groq C evaluation

- Add source-grounded C cases, strict backend binding/coverage checks and first-review regression validation; preserve failed trials in the evaluation record.
- Evaluate Qwen through the existing Groq key after inconsistent GPT-OSS reviewer results; keep A unchanged and runtime integration pending.
- Pace calls with finite deadlines and no automatic retries; retain manual/full-suite and selected-case execution.

## 2026-11-02 — Explicit single-call Groq smoke

- Add a one-generation-call Groq mode using the previously verified model; no metadata refresh or retries.
- Stop automatic API calls on ordinary pushes; preserve selected-provider gating, deadlines and explicit incomplete results.

## 2026-11-02 — Groq model-access migration

- Replace the retired evaluation Llama ID with GPT-OSS 20B and verify presence/activity against Groq’s accessible model catalog.
- Select Groq alone in default readiness runs, report the selected model, and preserve its independent free-only guard. Production chat assignment remains unchanged.

## 2026-11-02 — Verified Gemini readiness profile

- Default evaluation readiness to Gemini 3.1 Flash-Lite/minimal after tiny JSON and three A-schema live trials passed; retain explicit overrides and failure history.
- Keep the wider diagnostic matrix manual-only. Runtime role assignment and technical-quality acceptance remain pending.

## 2026-11-02 — Gemini generation capability checks

- Require metadata to advertise generateContent and retain numeric HTTP error status for diagnosis.
- Replace the generation-rejected 2.5 diagnostic with a prespecified 3.1 Flash-Lite candidate; no production model assignment changes.

## 2026-11-02 — Gemini timeout diagnosis

- Compare tiny JSON and A-schema requests across prespecified thinking/model profiles under finite budgets; retain failures and require three A successes for a passing profile.
- Separate connection/read/write timeouts without exposing provider payloads. Runtime settings and provider assignments remain unchanged.

## 2026-11-02 — Isolated Gemini readiness

- Scope free-only evaluation confirmations per provider and select Gemini alone by default in Actions, using the owner-confirmed Gemini Free tier.
- Keep other provider keys absent from Gemini-only execution; validate selection and record the selected-provider call budget.

## 2026-11-02 — Bounded provider readiness

- Add evaluation-only Gemini/Groq/Mistral metadata probes and an isolated production-schema A clarification smoke, with finite deadlines, no retries and sanitized status summaries.
- Run through a main-branch/manual Actions workflow; inference requires explicit free-only account configuration. No role assignment or quality acceptance is implied.

## 2026-11-02 — Natural-question evaluation 0.2.0

- Replace source-hinted primary questions with 16 natural prompts; add 16 paraphrases and retain 14 hinted controls.
- Expand to 40 base cases with ambiguity, false-premise, missing/stale evidence, history and reviewer citation checks.
- Add input isolation and regression checks; retain source pins and pending domain/live acceptance.

## 2026-11-01 — Source-grounded evaluation baseline

- Add 32 versioned cases: 16 technical, 12 conversation/failure scenarios and 4 reviewer challenges, covering all 12 pinned specifications.
- Define development/locked splits, source-linked grading, trial records and separate retrieval, answer, reviewer and control metrics.
- Add no-key CI validation and optional original-PDF verification; domain approval, trial harness and live model results remain pending.

## 2026-11-01 — Repository consistency and clarification guard

- Synchronize current prototype/stack status, Gemini/Groq/Mistral shortlist, readiness instructions, immutable checkpoint tags and corrected M1 metadata.
- Align the implementation handoff with current API response fields, deletion behavior, pagination and SSE; restore Markdown table columns and add route/table drift checks.
- Prevent closing-mode collection or ready actions from reaching B with unresolved essential user-detail gaps or uncertain intent; bounded repair may ask clarification, otherwise the run stops.
- Add seven controller regressions; record 70 passing offline tests and 98 design/structure assertions, with live provider/domain acceptance still pending.

## 2026-10-31 — Chat actions in the sidebar

- Put accessible rename/delete icons beside every saved chat, available without opening it or scrolling to the header.
- Keep the current conversation intact when another chat is renamed/deleted; retain deletion confirmation and existing backend safeguards.
- Extend the browser journey to verify actions on both current and unopened chats.


## 2026-10-31 — Development prototype 0.1.0

- Implement local chat API/UI, durable history and A–B–C controller with exact review bindings, finite shared limits, clarification, cancel/retry and restart recovery.
- Add verified PDF ingestion, staged corpus builds, lexical/semantic retrieval, source inspection and explicit resumable embedding preparation.
- Add locked Python dependencies, runtime/browser regression suites, setup/backup instructions and checkpoint workflow.
- Synchronize current documentation and record real extraction gaps; live provider quality and full SRS acceptance remain pending.


This log tracks project documentation and design changes. SRS versions are document versions, not application releases.

## 2026-10-24 — Windows design-check compatibility

- Read all design-check text inputs explicitly as UTF-8 so Windows locale defaults cannot corrupt or reject repository documents.
- Run repository checks on Windows and Linux with Python 3.12; reject implicit text encodings in the design checker to catch regressions.

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

