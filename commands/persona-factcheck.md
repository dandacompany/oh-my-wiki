# persona-factcheck

Run the **fact-checker** persona over a document. Produces a sibling
markdown report at `<stem>.factcheck.md`.

## When to invoke

User says any of:

- "fact-check this"
- "verify the claims in <page>"
- "check the facts on <doc>"
- "팩트체크해줘"
- "이 글 사실 확인해줘"

## Inputs you need from the user

One of:

- Inline text → use `--text`
- File path → use `--file`
- Vault page → use `--vault-id <id> --vault-relpath <relpath>`

## Procedure

Dispatch the persona via `omw persona-run fact-checker` — this spawns an
isolated one-shot subagent on any backend (claude/codex/gemini/opencode)
with the persona spec as its system prompt. Show the user the result.

Pass the source document as input (via `--text`, `--file`, or
`--vault-id`/`--vault-relpath`). The subagent decomposes the document
into atomic claims, verifies each via `mcp__brightdata__search_engine`
(max 3 searches per claim), judges verdict + confidence, and writes a
markdown report to `<stem>.factcheck.md`.

After the subagent completes, show the report path and a 3-line summary
(supported / contradicted / unverifiable counts). If the source is in a
vault, run `omw reindex` to pick up the new report file.

## Common pitfalls

- **Source is `--text` (no origin).** The report needs an output path.
  If the user gave only text, write the report to a filename they specify
  or to `/tmp/`. Don't try to file it back to a vault that wasn't named.
- **MCP not available.** If `mcp__brightdata__search_engine` is
  unavailable, tell the user and offer to run with reduced rigor
  (mark every claim "unverifiable — search unavailable").
- **Source is huge (1000+ claim candidates).** Ask the user to
  scope (a section, a heading) before burning the search budget.
