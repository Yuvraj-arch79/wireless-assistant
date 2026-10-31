# Wireless Assistant

A local development assistant for clear, relevant and verifiable answers from a prepared **3GPP cellular** collection, with context-aware follow-up questions.

**Project stage:** First implementation checkpoint (v0.1.0); live provider and domain-quality acceptance remain pending.

**SRS:** v0.9.1 — 94 requirements and 30 acceptance scenarios.

**Application:** Local chat UI/backend, bounded A–B–C controller, ingestion and hybrid retrieval adapter implemented. Start with the [setup guide](docs/implementation/setup.md) and [verification record](docs/implementation/verification.md).

[Read the SRS PDF](docs/requirements/wireless-assistant-srs.pdf) · [Product brief](docs/product-brief.md) · [Documentation](docs/README.md) · [Roadmap](docs/roadmap.md) · [Open decisions](docs/decisions.md)

## Reproduce the source documents

The [corpus setup guide](corpus/README.md) locks the initial 12 NR PHY/Layer-2 specifications to exact Release 18 PDF versions and SHA-256 hashes. Original files are downloaded locally and remain outside Git.

```bash
python scripts/corpus.py fetch
python scripts/corpus.py verify
```

The acquisition utility supports Python 3.10+; the application uses Python 3.12. This step downloads verified PDFs only. Follow the setup guide to parse, embed, activate and run the chatbot.

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
| Acceptance scenarios and requirement mapping | Specified; prototype regression tests implemented, full acceptance pending |
| Initial role and control architecture | Documented |
| Detailed design and failure handling | Documented; [changes, design checks and pending acceptance](docs/design/verification.md) |
| Developer handoff | [Component connections, data contracts and implementation order](docs/design/implementation-guide.md) |
| Source inventory | [12 version-pinned Release 18 PDFs and reproducible acquisition](corpus/README.md); domain/coverage review remains in [#4](https://github.com/Yuvraj-arch79/wireless-assistant/issues/4) |
| Technology choices and baseline approval | Development defaults selected; benchmarking/acceptance open: [#5](https://github.com/Yuvraj-arch79/wireless-assistant/issues/5), [#6](https://github.com/Yuvraj-arch79/wireless-assistant/issues/6) |
| Parsing, indexing and retrieval | Implemented; real-corpus quality evaluation pending: [#7](https://github.com/Yuvraj-arch79/wireless-assistant/issues/7) |
| Runnable chatbot and product release | Development prototype available; needs local API key and prepared hybrid build; product acceptance pending |

Publishing documents in main makes them accessible; it does not mean proposed requirements are approved or the product has passed testing.

## Read or contribute

Start with the [documentation guide](docs/README.md). Use the [contribution guide](CONTRIBUTING.md) for changes and the [changelog](CHANGELOG.md) for document history.

The application runs locally with configured free cloud APIs. Prepared local documents do not remove the need for internet access to those APIs. Never commit an API key, conversations, PDFs or generated indexes.

## Run and verify

Use the [Windows/Linux setup instructions](docs/implementation/setup.md). After installing the locked dependencies:

```bash
python -m wireless_assistant.cli serve
```

Open **http://127.0.0.1:8765**. Saved chats are available immediately; AI answers require the configured free API and an activated hybrid corpus. No synthetic answer mode is exposed in the application.

```bash
python -m pytest -q
python docs/design/validate_design.py
```

Runtime tests use deterministic provider fixtures. Real corpus extraction was exercised; live generation, real embeddings, technical accuracy and full release acceptance remain unverified. The [verification record](docs/implementation/verification.md) separates those results and limitations. The setup guide also covers database backups, retained corpus builds and Git checkpoints.
