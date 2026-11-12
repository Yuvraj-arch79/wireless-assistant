# Complete TS 38.201 presentation setup

This isolated setup loads the **entire pinned TS 38.201 v18.0.0 Release 18 PDF**, not the two-sentence excerpt. Gemini produces document/query embeddings; Groq handles A and C; OpenRouter handles B. The original twelve-document manifest and existing chat folders remain available.

The source is a physical-layer **overview**. It describes other specifications but does not include their detailed contents. Unreadable extraction is excluded, and diagram/formula fidelity is not certified. Answers must cite the loaded document or explicitly identify missing evidence.

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

The live workflow tests these four cases through the real HTTP API/controller with at most six generation attempts per case, zero automatic retries/format repairs, persisted review checks and citation-to-source checks. Keyword checks are only coarse regressions; inspect the saved answers as well. Four successful probes do not certify every possible question. Calls to the same model are paced, so an answer can take about a minute.

## Validation record

Local implementation checks: 238 tests and 79 subtests passed; 98 structural/design assertions passed. Live results are recorded in the workflow artifact's `preparation.json` and `live-report.json`; the presence of this guide alone does not mean the live run passed.
