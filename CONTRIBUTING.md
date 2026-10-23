# Contributing

The repository is currently a requirements and initial-design project. There is no runnable assistant yet.

## Before changing behavior

Read the [product brief](docs/product-brief.md), [SRS](docs/requirements/wireless-assistant-srs.md) and [decision register](docs/decisions.md). Search existing issues before opening another one.

Describe the user problem, proposed behavior, affected requirement IDs and how the result can be checked. Keep open questions visible; do not turn a proposed model, quality target or configuration into an approved choice.

## Make a focused change

1. Create a short-lived branch from current main, such as `docs/clarification-policy`.
2. Keep the change focused and preserve unrelated user edits.
3. Update the relevant documents, requirements and acceptance scenarios together.
4. Explain the reason, resulting behavior, validation and remaining limitations in the PR.
5. Merge only when the intended scope and required checks are satisfied.

Keep useful history. Remove a file only when it is obsolete and its replacement or reason is clear. A merged source branch may be removed after its contents are safely available in main.

## Documentation checks

- Check relative links and file names.
- Preserve the five user problems and the A/B/C responsibility boundaries.
- Keep requirement IDs stable unless the behavior is intentionally removed.
- Keep statuses accurate: planned, documented, approved, implemented and tested mean different things.
- If the SRS changes, follow the [PDF rebuild and review process](docs/requirements/README.md).
- Record document changes in [CHANGELOG.md](CHANGELOG.md).
- For LLD, reference schema or limit changes, run `python docs/design/validate_design.py` and keep [design coverage](docs/design/verification.md) current. Report these as design checks, separately from application tests.

Acceptance scenarios describe application tests to perform later. Editing their text is not a passing test result.

## Local files and data

Use placeholder values in examples. Keep API keys, real conversations, source downloads, indexes and temporary build output out of version control. The repository ignores common local data and environment paths.

Add a reproducible application setup only after the stack is selected. Do not add badges, coverage numbers or performance claims that have not been measured.
