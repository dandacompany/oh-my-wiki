# persona-audit

Run the **wiki-auditor** persona to diagnose what's sick in the vault — broken
links, schema violations, stale/expired pages, orphan clusters, lint hotspots —
ranked by severity with the fixer to route to. Reads the deterministic health
reports first; prints a JSON triage to stdout. No file changes (auditor diagnoses;
librarian and the named ops/personas fix).

## When to invoke

User says: "audit the wiki", "what's wrong with my wiki?", "is the wiki healthy?",
"위키 점검해줘", "뭐가 문제야".

## Procedure

Gather the deterministic health signal for the active vault, then dispatch the
persona via `omw persona-run wiki-auditor` — an isolated one-shot subagent on any
backend (claude/codex/gemini/opencode) with the persona spec as its system prompt.

```bash
omw lint            # all categories (links/schema/stale/contradictions/orphans)
omw maint status    # stale / expired / lint_issues counts
omw report --json   # aggregate vault stats + health
omw connections     # orphan clusters / hubs / communities
```

Collect those JSON outputs and pass them as `--text` input to the subagent. The
subagent returns a JSON triage: `{summary:{critical,warning,info}, findings:[…]}`
where each finding carries `severity`, `kind`, `page`, `detail`, and `fix_with`.

Show the triage to the user, ordered critical → warning → info. For each finding,
offer to route the fix to the named op or persona:

- structure (orphans / cross-links / merges) → **wiki-librarian**
- contradictions → **consistency-checker**
- glossary inconsistency → **terminology-manager**
- index drift → **curator**
- a page op → `omw supersede` / `omw merge` / `omw edit` / `omw visibility`

Apply nothing without confirmation. After any applied fix, run `omw reindex` and
report what changed. Pairs with `commands/persona-librarian.md` (sick → fix).
