# `move` — relocate a memo to another folder

**Mode:** memo
**Underlying script:** `scripts.memo_ops.move`

## Preconditions

Active vault must be memo-mode.

## Flow

1. Locate the target note. If the user did not give an exact relpath, call `search.query` (limit 5) and present matches via AskUserQuestion.
2. Show available destination folders (immediate subdirs of `vault.path`, excluding `.trash` and the current folder). Allow `Other` for a new folder name.
3. Confirm move: "Move `<relpath>` → `<dest_folder>/<filename>`. Proceed?"
4. On confirm:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import memo_ops, registry
db = registry_path()
vault = registry.get_active(db)
new_relpath = memo_ops.move(
    db, vault_id=vault['id'],
    relpath='<old_relpath>', dest_folder='<dest_folder>',
)
print(new_relpath)
"
```

5. Report the new relpath.

## Error handling

- Destination folder does not exist → `memo_ops.move` creates it; mention this.
- Filename collision at destination → `memo_ops.move` auto-suffixes (`-2`, `-3`); report the final name.
- Source not found → re-prompt with a broader search.

## Ask (omw-ask)

This op's user fork is decision class `move-backlinks`. Surface it as a **structured choice** per the omw-ask convention (see SKILL.md + the `omw-ask` managed block) with the safe default **Rewrite backlinks** offered first; honor the session-sticky and non-interactive degrade rules.
