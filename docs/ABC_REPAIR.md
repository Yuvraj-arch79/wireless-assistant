# Restore the documented A → tools → B → C flow

This supersedes the temporary `fix_clause_flow.py` bypass. A is called for exact-clause questions too: it resolves the need and requests retrieval, B alone writes, and C reviews the exact candidate and original evidence. No hardcoded technical answer or provider fallback was added.

Changes:
- A transport uses action-specific JSON Schema branches, rather than null-padded fields from unrelated actions. Original-message references use short server-bound aliases on the wire; exact hashes, offsets and IDs are restored before backend validation. Unknown aliases are rejected.
- Empty passage expansions are invalid. Expansion is excluded from the initial wire schema when no passages exist.
- The full serialized A request, schema and reserved output count toward the observed 8,000-token allowance with a 1,000-token margin. Duplicate evidence metadata is removed from tool results; original question and clarification replies remain intact. B/C still receive complete evidence. A request that cannot fit stops before network dispatch; HTTP 413 is not retried unchanged.
- Clarification must identify a material user-detail/history gap tied to known requirements. Prompts prohibit asking users to choose factual answers or reconfirm requested language, analogy or citations. This structural check cannot prove all model clarification choices are semantically necessary.
- B is instructed to explain in the requested language, use clearly labelled faithful analogies, and disclose unsupported rationale. C still checks every factual claim and the exact candidate.
- Mixed-profile operation deadline is 60 seconds (run remains bounded to 300 seconds); HTTP read deadlines are 45 seconds for B and 30 seconds for A/C, connect 8 seconds. Provider timeout/status messages identify the role. Dispatch/result logs contain no keys or prompt/response bodies. External provider availability is not guaranteed.
- Runtime tokenizer initialization refuses an absent/corrupt local cache immediately, avoiding a hidden download during a request. Installer initializes it in a separate process with a 35-second deadline.

The one shared format repair, bounded retries, original source/version bindings, cancellation/recovery and two correction rounds remain in place. Keys, billing, model choices and PDF/index content are unchanged.

## Windows local patch

Stop the server. In the existing project PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install "tiktoken==0.14.0" "jsonschema==4.26.0" pytest
.\.venv\Scripts\python.exe "$env:USERPROFILE\Downloads\fix_abc_flow.py"
```

The installer modifies the affected provider functions and small engine/prompt/config sections, preserves unrelated code, saves a timestamped backup and restores its edits if checks fail. It supports the prior budget wrapper and clause bypass. An unrecognized patch location stops before writing. Do not rerun the superseded installers.

After `ABC FIX INSTALLED`, restart in the same PowerShell containing the already-tested environment keys:

```powershell
.\.venv\Scripts\python.exe -m wireless_assistant.cli --data-dir "$env:USERPROFILE\Downloads\dataone-pdf-ready" serve
```

Use **New chat** and the original TS 38.201 clause 4.2.3 Hinglish question. Logs must show A dispatch; B writes; C must accept before an answer is released. A successful API response alone is not an accepted answer. When provider capacity is being paced, a new HTTP log entry will not appear until dispatch.

## Verification and limits

13 November 2026: 258 offline tests passed, 79 subtests passed, 1 optional browser test skipped. Tests cover A being retained, retrieval/B/C handoff, rejection preventing release, clarification repair, aliases/invalid IDs, empty expansions, budget overflow/no dispatch, B/C preservation, HTTP 413/no retry, timeout privacy, cancellation and shared bounds. The installer is separately rehearsed against the old budget wrapper and clause bypass, including a second installation and preservation of an unrelated local edit.

No live provider keys were available in the repair environment. This is not a claim of live Hinglish answer quality or provider availability; the local live acceptance check remains required. CI on Windows and the optional browser suite must still pass before merge.
