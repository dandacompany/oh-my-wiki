# persona-consistency

Run the **consistency-checker** persona to surface contradictions
within a doc or across a vault. JSON report to stdout.

## When to invoke

- "check this doc for contradictions"
- "any inconsistencies in my wiki?"
- "이 글에 모순 있어?"
- "위키 안에서 어긋난 부분 찾아줘"

## Inputs

- Single doc mode: `--text`, `--file`, or `--vault-relpath` + `--vault-id`
- Vault-wide mode: `--vault-id` only (no source)

## Procedure

Dispatch the persona via `omw persona-run consistency-checker` — this spawns
an isolated one-shot subagent on any backend (claude/codex/gemini/opencode)
with the persona spec as its system prompt. Show the user the result.

Pass the source as input. In vault-wide mode, first gather the candidate
list (`omw lint`) and feed the
`contradiction_candidates` output to the subagent. In single-doc mode,
pass the source directly.

The subagent classifies each candidate pair as `confirmed` / `nuanced` /
`false_positive` with a 1-2 sentence explanation per verdict, then emits
JSON following the persona's output format.

Summarize to the user: counts per category + the most important confirmed
contradictions.

## Pitfalls

- **wiki_lint returned [].** Tell user there's nothing to judge.
- **Single-doc mode but doc is < 200 chars.** Probably nothing to
  contradict; tell user.
