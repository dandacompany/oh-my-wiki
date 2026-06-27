# `delete` — soft- or hard-delete a memo

**Mode:** memo
**Underlying script:** `scripts.memo_ops.delete`

## Preconditions

Active vault must be memo-mode.

## Flow

1. Locate the target note. If the user did not give an exact relpath, call `search.query` (limit 5) and present matches via AskUserQuestion.
2. Ask **soft** (default, moves to `.trash/<ts>-<stem>.md`) or **hard** (irrecoverable).
3. If **hard**, require a second confirmation prompt that names the file explicitly. Refuse if the user does not type the slug back, or if they pick "Cancel".
4. Call:

```bash
python3 -c "
from scripts.paths import registry_path
from scripts import memo_ops, registry
db = registry_path()
vault = registry.get_active(db)
result = memo_ops.delete(
    db, vault_id=vault['id'],
    relpath='<relpath>', hard=<True|False>,
)
print(result)  # trash relpath or None
"
```

5. Report:
   - Soft: "Moved to `<trash_relpath>`. Restore by moving the file back."
   - Hard: "Deleted permanently."

## Error handling

- Source not found → re-prompt with a broader search.
- User aborts second confirm on hard delete → fall back to soft delete or cancel.

## Ask (omw-ask)

This op's user fork is decision class `delete-page` (⚠destructive — never session-stickied; always re-ask). Surface it as a **structured choice** per the omw-ask convention (see SKILL.md + the `omw-ask` managed block) with the safe default **Cancel** offered first; honor the session-sticky and non-interactive degrade rules.
