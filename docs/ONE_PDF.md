# Complete TS 38.201 presentation setup

This isolated setup loads the **entire pinned TS 38.201 v18.0.0 Release 18 PDF**, not the two-sentence excerpt. Gemini produces document/query embeddings; Groq handles A and C; OpenRouter handles B. The original twelve-document manifest and existing chat folders remain available.

The source is a physical-layer **overview**. It describes other specifications but does not include their detailed contents. Unreadable extraction is excluded, and diagram/formula fidelity is not certified. Answers must cite the loaded document or explicitly identify missing evidence.

## Download the prepared index (recommended)

[Download the verified one-PDF artifact](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/43186016545/artifacts/13928049122) while signed into GitHub. It is retained for seven days. Extract it into `data/one-pdf` in the repository; `assistant.sqlite3` must sit directly inside that folder. It includes the verified source, complete Gemini index and public test chats. With this download, **skip `prepare-one`** below and run only `serve`. The local three API keys are still needed for new questions. If the artifact has expired, `prepare-one` recreates it from the pinned source.

## Windows PowerShell

From your existing repository folder:

```powershell
git pull --ff-only origin main
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
$env:WA_PROVIDER_PROFILE = 'groq_openrouter'
$env:WA_FREE_TIER_CONFIRMED = '1'
$env:WA_GROQ_FREE_TIER_CONFIRMED = '1'
$env:WA_OPENROUTER_FREE_TIER_CONFIRMED = '1'
```

Enter each key privately without putting it in the command history:

```powershell
foreach ($name in @('GEMINI_API_KEY','GROQ_API_KEY','OPENROUTER_API_KEY')) {
    $secret = Read-Host $name -AsSecureString
    $credential = New-Object System.Net.NetworkCredential('', $secret)
    [Environment]::SetEnvironmentVariable($name, $credential.Password, 'Process')
}
```

GitHub Actions secrets are not automatically available on your laptop. Keep this PowerShell window open. Do not commit keys or post them in chat.

```powershell
.\.venv\Scripts\python -m wireless_assistant.cli prepare-one
.\.venv\Scripts\python -m wireless_assistant.cli --data-dir data/one-pdf serve
```

Open http://127.0.0.1:8765. The badge and loaded-source list must say **TS 38.201**. The first command verifies the pinned SHA-256, extracts the whole PDF, prepares compatible Gemini vectors and activates only a complete index. It saves progress and stops on quota failure; rerunning resumes successful batches. It cannot guarantee that a free account has quota.

To avoid repeating document embedding, download a successful **One PDF live validation** workflow's `one-pdf-validation` artifact and extract its contents into `data/one-pdf` (so `data/one-pdf/assistant.sqlite3` exists). Then run only the serve command. Query embedding still needs Gemini access. Do not replace an existing chat database: back up that folder first or use a separate folder with `--data-dir`.

## Demonstration questions

- Which specification series describes Layer 1 and which describes Layers 2 and 3? (4.1.1)
- What channel coding is used for transport blocks versus PBCH/control information? (4.2.3)
- What control procedures are in the scope of TS 38.213? (5.6)
- Give the exact numerical LDPC base-graph selection thresholds. (Not specified in this overview; must acknowledge missing detail.)

The live workflow tests these four cases through the real HTTP API/controller with at most seven generation attempts per case, zero automatic retries and at most one format repair, persisted review checks and citation-to-source checks. Keyword checks are only coarse regressions; inspect the saved answers as well. Four successful probes do not certify every possible question. Calls to the same model are paced, so an answer can take about a minute.

## Source extraction

All pages of the pinned PDF are processed into 50 passages. Of these, 36 are eligible for embedding; 14 are excluded (front matter, problematic table/diagram extraction or mathematical glyphs). Exclusion is explicit: full-PDF ingestion does not mean perfect extraction of every figure or formula. The main overview clauses 4.1.1–4.2.5 and specification summaries 5.2–5.9 have readable text.

## Validation record

Local implementation checks: 238 baseline tests plus two citation-repair regressions passed (240 total), with 79 subtests; 98 structural/design assertions passed. Live validation on 12 November 2026:

| Probe | Result | Source |
| --- | --- | --- |
| Layer 1 versus Layers 2/3 specification series | Accepted C review; cited answer | 4.1.1 |
| Transport-block coding versus PBCH/control coding | Accepted C review; cited answer; one bounded B format repair | 4.2.3 |
| TS 38.213 control-procedure scope | Accepted C review; cited answer on targeted recheck | 5.6 |
| Exact LDPC thresholds absent from this overview | Explicit insufficient-evidence stop; no invented thresholds or unchecked draft | Out of loaded coverage |

[Initial four-case run](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/43184708258) passed three cases; the control question failed at Groq A with `PROVIDER_UNAVAILABLE`. [Only that question was rerun](https://github.com/Yuvraj-arch79/wireless-assistant/actions/runs/43186016545) and passed. Thus four representative probes passed across two runs, **not one flawless full-suite run**. The final artifact retains the index and saved public chat history; its `live-report.json` covers the targeted recheck. No additional document embedding was needed on either rerun.

The complete index has 36 Gemini vectors, created in three batches. The three successful answers also passed backend citation/version binding checks and C review; their text was compared with the pinned source clauses. This is a presentation-ready scoped prototype, not an assurance of every answer or provider uptime. Free provider quota, availability and formula/diagram extraction remain limitations.
