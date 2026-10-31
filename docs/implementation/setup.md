# Run the development prototype

This is v0.1.0, a development build of the agreed A–B–C architecture. It is not a release acceptance or model-accuracy certificate. Read [verification and limitations](verification.md) before relying on technical answers.

## 1. Install from the clone

Use **Python 3.12**, a terminal in the repository root, and a new virtual environment. Keep the clone on a local disk. Do not expose the server to a network.

Windows Command Prompt:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m pytest -q
python docs/design/validate_design.py
```

Linux/macOS: replace the first two commands with `python3.12 -m venv .venv` and `source .venv/bin/activate`. macOS is not a verified platform. Run all following commands in this activated environment, from the clone root. Editable installation is the supported layout; do not relocate the installed package away from the source manifest.

## 2. Start the UI immediately

```bash
python -m wireless_assistant.cli serve
```

Open **http://127.0.0.1:8765** in the browser. The terminal stays open while the server runs; Ctrl+C stops it. Chat management is available before AI setup. The UI disables answer generation until a compatible hybrid corpus and server API configuration exist. It never substitutes canned answers.

Stop the server before ingestion, embeddings, activation or backup; maintenance and the server share a data-directory lock. All generated state stays under ignored `data/app/`. `WA_DATA_DIR` may select a different absolute directory; `WA_PORT` may select another loopback port. Do not run multiple server processes against one database.

## 3. Obtain and inspect the corpus

```bash
python scripts/corpus.py fetch
python scripts/corpus.py verify
python -m wireless_assistant.cli ingest
python -m wireless_assistant.cli builds
```

Save the printed **lexical build ID**. In commands below, replace `LEXICAL_BUILD_ID` with that value; do not type the placeholder literally.

```bash
python -m wireless_assistant.cli search "RLC segmentation reassembly" --build LEXICAL_BUILD_ID
```

This previews extracted passages; it does not ask an AI or establish answer quality. Ingestion rechecks every file hash and size, stages a build and preserves the old active build on failure. It has a 600-second invocation deadline and 120-second per-document bound. Very slow machines may need a reviewed limit adjustment. A failed build remains visible for diagnosis; it is not automatically retried indefinitely.

The parser retains clause, page, document version, original hash, table cells and cross-reference metadata. It excludes known unreadable text and front matter. Equations, diagrams and complex tables still need manual inspection of the original PDF. See the measured gaps in the verification record.

## 4. Configure free API access on your computer

Use your own Gemini API project with **billing disabled** and model access available. Never paste the key into a chat, issue, screenshot or Git file. The application does not inspect your billing account: `WA_FREE_TIER_CONFIRMED=1` records your confirmation, not a server-side billing guarantee. There is no automatic paid/provider fallback, built-in web search or provider file-search service.

Windows Command Prompt (current terminal only):

```bat
set GEMINI_API_KEY=YOUR_PRIVATE_KEY
set WA_FREE_TIER_CONFIRMED=1
```

Linux/macOS:

```bash
export GEMINI_API_KEY='YOUR_PRIVATE_KEY'
export WA_FREE_TIER_CONFIRMED=1
```

Defaults are `gemini-3.8-flash` for each independent A, B and C call, and `gemini-embedding-001` with 768 dimensions. Optional `WA_MODEL_A`, `WA_MODEL_B`, `WA_MODEL_C` override generative IDs; they do not silently fall back if unavailable. Treat any model change as a new evaluation. Embedding changes require a reviewed compatible rebuild. Availability and free quotas depend on your project and may change.

Provider calls send the selected question/history, retrieved passages and role instructions to Google. Free-tier data terms can permit product improvement; use public standards and nonsensitive test questions initially. Local chat deletion cannot delete provider-side records or your separate backups. See the official [model catalog](https://ai.google.dev/gemini-api/docs/models), [pricing/data-use table](https://ai.google.dev/gemini-api/docs/pricing) and [embedding API](https://ai.google.dev/api/embeddings). Development defaults were checked against these pages on 31 October 2026; no live model benchmark was performed.

## 5. Prepare the hybrid index

```bash
python -m wireless_assistant.cli embed LEXICAL_BUILD_ID --max-batches 20
```

Each invocation performs at most 20 synchronous embedding batches of at most 16 passages, with a 600-second overall bound. Completed batches persist. If it prints `complete: false`, run that exact command again when your quota permits. **Do not wrap it in an endless retry loop.** A quota/error stops the command; it never activates a partial index. `batchEmbedContents` here is the synchronous embedding method, not the paid asynchronous Batch service.

When `complete: true` appears, save its **hybrid build ID**:

```bash
python -m wireless_assistant.cli activate HYBRID_BUILD_ID
python -m wireless_assistant.cli status
python -m wireless_assistant.cli serve
```

`ready: true` means local configuration/index prerequisites exist; it does not prove the API key works or the model answers correctly. Ask one simple question and inspect its cited clause. Then try a follow-up, clarification, cancel and restart. Record real provider outcomes and compare answers with original PDFs before a pilot.

## 6. Check, back up and return to a checkpoint

```bash
python -m pytest -q
python docs/design/validate_design.py
python -m wireless_assistant.cli backup data/backup-before-change.sqlite3
```

Backups use SQLite's backup API and integrity checks; destination must not already exist. Keep backups private and outside Git. Schema v1 is recognized explicitly; unsupported schemas fail rather than resetting data. Code checkpoints and local data backups solve different problems.

For code rollback, keep the current clone and create a separate worktree from a recorded commit/tag:

```bash
git fetch origin --tags
git worktree add ../wireless-assistant-checkpoint CHECKPOINT_REF
```

Create its own virtual environment and use a **different `WA_DATA_DIR`**. The existing `baseline-before-prototype` tag preserves pre-implementation commit `3e924297fa88dbdbe7f16497d10d9dfd42afe695`. The prototype tag is `prototype-v0.1.0` only after the successful main-branch checkpoint workflow creates it; confirm with `git tag -l`. Never force-move a tag.

To restore local data, stop the server, keep the entire current data directory, and copy a verified backup to a new directory as `assistant.sqlite3`. Point `WA_DATA_DIR` at that new directory. Do not overwrite a live database or combine an old main database with newer WAL/SHM files. To roll back only the corpus, use `activate PREVIOUS_VALIDATED_BUILD_ID`; retained builds keep existing citations resolvable.

Optional browser check:

```bash
python -m pip install -r requirements-browser.lock
python -m playwright install chromium
```

Set `WA_BROWSER_TEST=1`, then run `python -m pytest tests/runtime/test_browser.py -q`. This test uses a clearly synthetic provider and tiny corpus; it verifies UI behavior, not 3GPP answer accuracy. Linux CI installs browser system dependencies with `playwright install --with-deps chromium`.
