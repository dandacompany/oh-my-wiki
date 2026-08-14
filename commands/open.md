# `open` — open a note in the editor

**Mode:** memo or wiki (any active vault)
**Underlying script:** `scripts.adapters.get_adapter(...).open(...)` (Plan A)

## Preconditions

Active vault must exist.

## Flow

1. If the user did not give an exact relpath, call `search.query` (limit 5) — same as `find` — and present matches via AskUserQuestion.
2. Open:

```bash
omw view <relpath>
```

- For `vault.type == 'markdown'`: opens via OS default (`open` on macOS, `xdg-open` on Linux, `start` on Windows).
- For `vault.type == 'obsidian'`: opens via `obsidian://open?vault=<name>&file=<relpath>` URI (handled inside `ObsidianAdapter`).

3. Confirm to the user: "Opened `<relpath>` via <adapter>."

## Error handling

- File does not exist → suggest `lint` (drift detection).
- Obsidian not installed but `vault.type == 'obsidian'` → the URI will be rejected by the OS; offer to retry with `vault-use` switching to a markdown vault.
