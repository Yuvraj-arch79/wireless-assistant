# Wireless Assistant requirements

The SRS describes the agreed product and the proposed implementation baseline in plain English.

- [Read the PDF](wireless-assistant-srs.pdf)
- [Read or edit the Markdown source](wireless-assistant-srs.md)
- [Related product brief review (PR #2)](https://github.com/Yuvraj-arch79/wireless-assistant/pull/2)

**Version:** 0.9, dated 12 October 2026. **Status:** review draft; no product approval or implementation test pass is implied.

The document covers the user problems and goals, cellular scope, domain checks, clarification, history, prepared 3GPP RAG, A/B/C responsibilities, bounded correction, evidence and citations, final delivery, privacy, operation, quality measures, acceptance scenarios, traceability, risks and open decisions.

There are 94 identified requirements, each with a check, and 30 acceptance scenarios. CONFIRMED requirements reflect the agreed design. PROPOSED requirements and numerical quality targets require baseline review. Exact source coverage, API/model choices and operating limits are intentionally left as explicit decisions.

The existing product brief remains a separate draft. This SRS makes the division of model responsibilities explicit: A gathers context, B writes and revises, C judges, and backend code delivers the eligible B answer.

## Rebuild the PDF

Use Python 3.10 or newer, ReportLab 4, and the DejaVu Sans regular and bold fonts. Install the documentation dependency in a virtual environment:

```bash
python -m pip install -r requirements-docs.txt
python build_srs.py
```

Run these commands from this directory. If DejaVu Sans is installed elsewhere:

```bash
python build_srs.py --font-dir /path/to/dejavu-fonts
```

The PDF is generated from `wireless-assistant-srs.md`. The source uses a small Markdown subset: one section per `##` heading, `###` subheadings, paragraphs, simple bullet lists, pipe tables, quoted notes and the workflow diagram. Table width comments control layout. Requirement entries use a stable ID, a Status line, a requirement paragraph and a Check line.

The workflow's PDF drawing is implemented in `build_srs.py`; keep it aligned with the Mermaid diagram if the workflow changes. The renderer refuses a section that does not fit its page rather than silently clipping it. Split an overlong section or simplify its wording; do not shrink text until it becomes difficult to read.

## Change and review

1. Edit the Markdown source; preserve requirement IDs unless behavior is intentionally removed.
2. Update the version, affected checks, traceability and open decisions when behavior changes.
3. Rebuild the PDF, inspect every changed page and check the contents links and source links.
4. Commit the matching Markdown and PDF in the same pull request.

Document verification is different from application testing. The acceptance scenarios describe tests to run during implementation; they have not been claimed as passed by this documentation change.
