# Maintainer guide

Short, task-focused notes for the next developer. Each rule has one owner module; change it there.

| Rule | Owner | Test that catches a regression |
| --- | --- | --- |
| Provider wire format, HTTP status → app error code, wait time | `role_provider.py` (Groq), `provider.py` (Gemini) | `tests/runtime/test_groq_b.py`, `test_a_transport.py`, `test_failure_reporting.py` |
| A/B/C state machine, budgets, release of the exact reviewed text | `engine.py` + `validation.py` | `tests/runtime/test_flow.py`, `test_c_decision.py` |
| Which document version answers a message | `versions.py` | `tests/runtime/test_versions.py` |
| What the user is told when a run stops for a technical reason | `failures.py` | `tests/runtime/test_failure_reporting.py` |
| Developer run log (no keys, no chat text) | `runlog.py` | `test_run_log_has_stage_model_and_no_secrets_or_chat_text` |
| Archive inventory and pre-activation sample citations | `corpus/ts38201_archive.json`, `Corpus.verify_samples` | `test_archive_inventory_is_honest`, `test_activation_sample_check_failure_keeps_old_build` |
| Live answer quality (language, follow-ups, scope) | `evaluation/conversation_live.py` | the live workflow below; `tests/test_conversation_eval.py` checks the checker |

A provider returning HTTP 200 is never treated as a valid answer: the JSON must pass the role
contract (`contracts.py`), the backend checks (`validation.py`) and C's review of the exact text.

## Change the AI provider or its response format

1. Edit only the adapter: `role_provider.build_request` (request body/schema) and `generate`
   (turn the provider response into the role JSON). Keep the engine contract: return
   `{'text': <role JSON>}` or `{'contract_error': ...}` for the single bounded repair, or raise
   `AppError` with a code that `failures.py` knows (add one line there if it is new).
2. Map HTTP failures in `request`: 413 → `PROVIDER_REQUEST_TOO_LARGE` (never resent unchanged),
   429 → `PROVIDER_QUOTA` with `retry_after` from the provider, 5xx → `PROVIDER_UNAVAILABLE`.
3. Update the adapter tests with a recorded (redacted) response of the new format. Chat
   history, retrieval, validation and the UI should not change.
4. Run `python -m pytest -q`, then the live check (below). Roll back by reverting the adapter
   commit; stored chats and the index are unaffected.

## Add a new TS 38.201 version

The archive inventory lists all 15 archive versions with SHA-256; only v18.0.0 is indexed.

1. Back up first: `python -m wireless_assistant.cli --data-dir data/one-pdf backup data/backup-<date>.sqlite3`.
2. Replace the TS 38.201 entry in `corpus/manifest.json` with the new version's pinned source
   (exact URL, SHA-256, size, pages; `prepare-one` indexes exactly one 38.201 entry) and add its
   `activation_checks` (clause + words that must be readable) in `corpus/ts38201_archive.json`.
   Mark the archive entry `indexed` (and the old one `not_indexed`) only after step 3 passes.
3. `python -m wireless_assistant.cli --data-dir data/one-pdf prepare-one` verifies the checksum,
   extracts into a **new build next to the old one**, embeds, runs the sample-citation checks and
   only then switches the active pointer. Any failure leaves the previous build active.
4. Ask a few questions and open their sources. Old chats keep opening the passages they were
   answered from (evidence is snapshotted per answer). A chat whose earlier answers used another
   version is told to start a new chat or name the version; versions are never mixed.
5. Roll back: `cli builds` lists builds; `cli activate <previous build id>` switches back
   (builds are immutable and retained). Revert the manifest commit.

The current parser reads the ETSI PDF; the 3GPP archive ZIPs contain Word files and are not
parsed yet. Indexing a ZIP directly needs a Word parser first.

## Trace a failed run from its ID

Every technical stop shows a reference such as `(Ref: run f5471590, PROVIDER_REQUEST_TOO_LARGE)`.

```powershell
.\.venv\Scripts\python -m wireless_assistant.cli --data-dir data/one-pdf trace f5471590
```

The output has the run status, stage (A understand/search, B write, C review), stop code,
counters, each provider/tool operation and the log lines from `data/one-pdf/logs/runs.jsonl`
(provider, model, elapsed ms, token estimate, retry/repair, error code). Example from the
18 Nov live run on main: A's second call carried ~35 KB after search and Groq returned 413;
the log shows `stage=A code=PROVIDER_REQUEST_TOO_LARGE token_estimate=35134`.

## Live check (real providers, free tier)

Push a commit that changes `.github/live-trigger` on a `fix/**` branch, or run the
"Conversation live check" workflow. Results go to a throw-away branch
`ci/live-results-<run id>`; read `conversation-report.json` (released text + cited passage
text) and delete that branch afterwards. Automatic checks are coarse; read the answers.

## Design check: what changes, what catches it, how to go back

| If tomorrow… | Component that changes | Test that catches the mistake | Return to the working version |
| --- | --- | --- | --- |
| Groq changes its response format | `role_provider.py` only | adapter tests (`test_groq_b.py`, `test_a_transport.py`), then live check | revert the adapter commit |
| A new TS 38.201 version appears | `corpus/manifest.json`, `ts38201_archive.json` (new build in the same folder) | checksum + `verify_samples` before activation, `test_versions.py` | `cli activate <previous build id>` |
| A Hinglish follow-up regresses | `prompts.py` (and its prompt version in `config.py`) | live `B_followup_same_chat` / `B_fresh_chat_isolation` cases; offline `test_same_chat_follow_up_sees_history_fresh_chat_does_not` | revert the prompt commit (prompt version is recorded in every run's config snapshot) |
