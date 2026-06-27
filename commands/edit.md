# `edit` — modify an existing memo

**Mode:** memo
**Underlying script:** `scripts.memo_ops.edit_meta` (frontmatter field) or open file in editor (body)

## Preconditions

Active vault must be memo-mode. Run `python3 -m scripts.wizard status` first.

## Flow

1. Ask the user **what** to edit:
   - Option A: A single frontmatter field (title, tags, status, summary, ...)
   - Option B: The body (opens the file in the user's editor / Obsidian via adapter)
   - Option C: Cancel

### Option A — frontmatter field

1. Locate the target note. If the user mentioned a title or partial slug, call `search.query` (limit 5) and present matches via AskUserQuestion. If they referenced an exact `relpath`, skip the search.
2. Ask which field to edit (multi-select not allowed — one field per invocation; loop if needed).
3. For the chosen field, ask for the new value. For `tags`, accept a comma-separated string and split into a list.
4. Call:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import memo_ops, registry
db = registry_path()
vault = registry.get_active(db)
memo_ops.edit_meta(
    db, vault_id=vault['id'],
    relpath='<relpath>', key='<field>', value=<value>,
)
"
```

### Option B — body

1. Locate the target note (same search flow).
2. Open via the vault's adapter:

```bash
python3 -c "
from pathlib import Path
from scripts.paths import registry_path
from scripts import adapters, registry
db = registry_path()
vault = registry.get_active(db)
a = adapters.get_adapter(vault['type'], vault_name=vault['name'])
a.open(Path(vault['path']) / '<relpath>')
"
```

3. Tell the user the file is open; ask them to confirm when done. On confirm, run incremental reindex:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import reindex, registry
db = registry_path()
vault = registry.get_active(db)
reindex.incremental(db, vault_id=vault['id'])
"
```

## Post-conditions

- File contains the updated content; `notes` table mtime is current.
- Confirmation back to the user: which field/file, and the new value (for frontmatter edits).

## Error handling

- Note not found → re-run search with broader limit, or ask for exact relpath.
- Invalid frontmatter (rare; only if existing file was hand-broken) → suggest `lint` and stop.

## Ask (omw-ask)

This op's user fork is decision class `new-vs-update`. Surface it as a **structured choice** per the omw-ask convention (see SKILL.md + the `omw-ask` managed block) with the safe default **Propose as new** offered first; honor the session-sticky and non-interactive degrade rules.
