# persona-librarian

Run the **wiki-librarian** persona to propose structural fixes (cross-links,
orphan resolution, merges). Reads the F#1 link graph first; prints JSON
proposals to stdout. No file changes until you confirm.

## When to invoke

User says: "tidy the wiki structure", "what's orphaned?", "suggest cross-links",
"위키 구조 정리해줘".

## Procedure

Dispatch the persona via `omw persona-run wiki-librarian` — this spawns an
isolated one-shot subagent on any backend (claude/codex/gemini/opencode)
with the persona spec as its system prompt. Show the user the result.

Before dispatching, gather the deterministic link graph for the active vault:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import links, registry
import json
db = registry_path(); vid = registry.get_active(db)['id']
print(json.dumps({'orphans': links.orphans(db, vid), 'graph': links.graph(db, vid)}))
"
```

(If that one-liner is awkward, run `omw lint` and read its `links` section,
which already contains `orphans`/`broken`.)

Pass this JSON as `--text` input to the subagent. The subagent produces JSON
proposals (add cross-links, move orphans, merge candidates).

Show proposals and ask which to apply (propose → confirm → execute). On
confirm, apply the chosen edits and run `omw reindex`. Report what changed.

For a mutation proposal (curator's `index.md` rewrite), review the staged
`.proposed.md` and confirm before
`omw persona-run wiki-librarian --apply <proposal>`.
