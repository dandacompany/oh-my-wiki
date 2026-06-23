# persona-terminology

Run the **terminology-manager** persona to build/refresh the
per-vault glossary and surface inconsistent surface forms.

## When to invoke

- "build a glossary for this vault"
- "what terms does my wiki use?"
- "any inconsistent terminology?"
- "용어집 만들어줘"
- "용어가 일관되게 쓰였는지 확인해줘"

## Inputs

- `--vault-id <id>` (required)
- Optional: `--vault-relpath <relpath>` to scope ingestion to a
  single page on this run (otherwise scan all wiki/ pages)

## Procedure

Dispatch the persona via `omw persona-run terminology-manager` — this spawns
an isolated one-shot subagent on any backend (claude/codex/gemini/opencode)
with the persona spec as its system prompt. Show the user the result.

Pass `--vault-id` (and optionally `--vault-relpath`) as input. The subagent
scans wiki pages, extracts candidate terms per the persona's "What counts as
a term" rules, upserts new terms into the glossary DB, runs lint, and emits
JSON following the persona's output format.

Summarize to the user: total terms in glossary, N added this run, K
inconsistencies flagged, top 3 suggested actions.

## Pitfalls

- **No wiki/ directory** (memo mode vault). Tell user
  terminology-manager is wiki-mode specific.
- **Tens of thousands of candidates.** Cap at ~50 new terms per
  run; tell user to re-run.
- **`.oh-my-wiki/glossary.db` already exists.** Fine — that's
  the steady state. Just keep upserting.
