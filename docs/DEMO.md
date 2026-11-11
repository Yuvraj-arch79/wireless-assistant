# Live A–B–C demo

The mixed runtime profile connects **A: Groq GPT-OSS 120B**, **B: OpenRouter Nemotron 3.5 Super VL free**, and **C: Groq Qwen 3.8 27B** to the existing controller, database, citations, cancel/restart controls and chat UI. C uses 900 maximum output tokens and no separate reasoning tokens to fit the observed 1,000 OTPM account cap. This is a development profile; it is not a reliability certification.

## Quick presentation setup (Windows PowerShell)

In your cloned repository, stop the old server first, then:

```powershell
git pull --ff-only origin main
py -3.12 -m pip install -r requirements.lock
$env:GROQ_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Groq API key' -AsSecureString)).Password
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenRouter API key' -AsSecureString)).Password
$env:WA_GROQ_FREE_TIER_CONFIRMED = '1'
$env:WA_OPENROUTER_FREE_TIER_CONFIRMED = '1'
py -3.12 -m wireless_assistant.cli demo
```

Use confirmation `1` only for the free accounts you selected. Keys stay in this terminal's environment; do not commit them. GitHub Actions secrets do not automatically appear on your laptop. Open **http://127.0.0.1:8765** and select the first sample question. Stop with Ctrl+C. Close the terminal to discard its key environment.

The explicit demo command uses a **separate `data/demo` database** and one manually verified public excerpt from **TS 38.201 v18.0.0, clause 4.1.1, PDF page 7**. The source identity and exact excerpt are checked before readiness. It does not download or ingest the 12 full PDFs. Existing `data/app` chats/corpus are preserved. A banner and sample questions disclose this limited source coverage.

Example: “Which specification series describes Layer 1 and which describes Layers 2 and 3 in NR?” The source establishes 38.200 and 38.300 respectively. A selects the need and requests a real local search, B writes the cited answer, and C must approve the exact candidate/evidence/need/context versions before release. Queries requiring other source details should expose the missing coverage instead of inventing an answer.

## Bounds and full-corpus mode

Mixed provider calls to the same model start at least 65 seconds apart, shared across chats/resumes/repairs in one running server. Waiting consumes the run deadline and is cancelable. Restarting the app does not reset the provider's own quota. A quota response stops the run without automatic retry; no paid route or model fallback is used. C truncation or invalid output cannot release a draft. Default mixed runs have a five-minute active deadline and retain the controller's existing finite corrections/call budgets.

For the existing full corpus, prepare and activate a compatible hybrid build using [setup guide](implementation/setup.md), set `WA_PROVIDER_PROFILE=groq_openrouter`, and run `py -3.12 -m wireless_assistant.cli serve`. Hybrid embedding still requires the configured Gemini embedding API and its free-tier confirmation. The demo command deliberately avoids that separate corpus preparation dependency; it does not claim to replace hybrid retrieval.

## Verification

The `Live A-B-C demo` Actions workflow exercises one real API chat through the real application/controller and local excerpt retrieval. It allows at most six generation attempts, no format repairs or retries, and succeeds only after a persisted accepted C review plus a cited final answer. Ordinary pushes skip live calls; manual dispatch or an explicitly authorized `[abc-demo]` commit runs it. The C diagnostic workflow remains separate. Live results are pending until the linked Actions run completes.
