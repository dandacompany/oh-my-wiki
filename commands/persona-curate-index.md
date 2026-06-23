# persona-curate-index

Run the **curator** persona to sync + reorder `wiki/index.md`. Reads the
deterministic `index_drift` report first; proposes a full rewritten index on
stdout. Nothing is written until you confirm.

## When to invoke

User says: "update the index", "the TOC is stale", "reorder the wiki index",
"목차 정리해줘".

## Procedure

Dispatch the persona via `omw persona-run curator` — this spawns an isolated
one-shot subagent on any backend (claude/codex/gemini/opencode) with the
persona spec as its system prompt. Show the user the result.

Before dispatching, compute drift for the active vault:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import links, registry
import json
db = registry_path(); vid = registry.get_active(db)['id']
print(json.dumps(links.index_drift(db, vid)))
"
```

(Or read `omw lint`'s `links.index_drift`.)

Pass the drift JSON plus the current `wiki/index.md` content as `--text`
input to the subagent. The subagent produces a proposed full rewrite of
`index.md`.

Show the proposed index.md and ask to apply (propose → confirm → execute).
For a mutation proposal (curator's `index.md` rewrite), review the staged
`.proposed.md` and confirm before
`omw persona-run curator --apply <proposal>`.

On confirm, write the proposed content to `wiki/index.md` and run
`omw reindex`. Re-run the drift check to confirm
`missing_from_index`/`dangling_in_index` are now empty. Report the result.
