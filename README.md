# Wireless Assistant

A planned assistant for clear, relevant and verifiable answers from a prepared **3GPP cellular** collection, with context-aware follow-up questions.

**Project stage:** Requirements review and detailed design.

**SRS:** v0.9.1 — 94 requirements and 30 acceptance scenarios.

**Application:** Not implemented yet.

[Read the SRS PDF](docs/requirements/wireless-assistant-srs.pdf) · [Product brief](docs/product-brief.md) · [Documentation](docs/README.md) · [Roadmap](docs/roadmap.md) · [Open decisions](docs/decisions.md)

## Reproduce the source documents

The [corpus setup guide](corpus/README.md) locks the initial 12 NR PHY/Layer-2 specifications to exact Release 18 PDF versions and SHA-256 hashes. Original files are downloaded locally and remain outside Git.

```bash
python scripts/corpus.py fetch
python scripts/corpus.py verify
```

Run from the repository root with Python 3.10+. This prepares verified source PDFs; parsing, indexing and the chatbot are not implemented yet.

## What the assistant will help with

- Understand concepts and procedures through suitable explanations and examples.
- Find relevant clauses in the declared 3GPP collection.
- Match the user's requested detail, comparison or procedure.
- Verify claims through inspectable source references.
- Continue follow-up questions using relevant conversation context.

The first release is limited to the selected 3GPP cellular documents. It will explain missing coverage and decline clearly unrelated requests.

## How the design works

| Part | Responsibility |
| --- | --- |
| A | Collect the needed source passages, history and clarification. |
| B | Write and revise the answer. |
| C | Judge B's answer and return specific findings. |
| Backend | Run tools, enforce limits and display the exact eligible B answer. |

C's findings go to **B first**. A is called during correction only when B identifies missing information. The workflow allows one initial draft and at most two correction rounds.

[Read the architecture](docs/architecture.md) for an overview, and the [system design and LLD](docs/design/system-design.md) for clarification, finite processing, review contracts, persistence, recovery and API behavior.

## Current status

| Work | Status |
| --- | --- |
| Product problem, users, goals and assumptions | Documented in the product brief |
| Functional and quality requirements | Complete review draft, SRS v0.9.1 |
| Acceptance scenarios and requirement mapping | Specified; application tests have not been run |
| Initial role and control architecture | Documented |
| Detailed design and failure handling | Documented; [changes, design checks and pending acceptance](docs/design/verification.md) |
| Developer handoff | [Component connections, data contracts and implementation order](docs/design/implementation-guide.md) |
| Source inventory | [12 version-pinned Release 18 PDFs and reproducible acquisition](corpus/README.md); domain/coverage review remains in [#4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) |
| Technology choices and baseline approval | Open: [#5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5), [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| First evidence pipeline | Planned: [#7](https://github.com/Yuvraj-arch79/wireless-assistant/issues/7) |
| Runnable chatbot and product release | Not available yet |

Publishing documents in main makes them accessible; it does not mean proposed requirements are approved or the product has passed testing.

## Read or contribute

Start with the [documentation guide](docs/README.md). Use the [contribution guide](CONTRIBUTING.md) for changes and the [changelog](CHANGELOG.md) for document history.

The intended application runs locally with configured free cloud APIs. Prepared local documents do not remove the need for internet access to those APIs. Providers and the application stack remain open decisions.

The executable utilities are the [corpus downloader/verifier](scripts/corpus.py), [SRS PDF renderer](docs/requirements/README.md#rebuild-the-pdf) and [design validator](docs/design/validate_design.py). They verify source identity or document/database mechanics; they do not run a chatbot or establish model accuracy. There is no chatbot installation command yet.
