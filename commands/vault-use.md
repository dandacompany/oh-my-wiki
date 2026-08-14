# `vault-use <name>` — switch the active vault

**Underlying script:** `scripts.registry.set_active`

## Flow

1. If `<name>` was provided in the user input, use it. Else, list vaults and ask via AskUserQuestion (max 4 options; if more vaults, ask for the name as free text).

2. Run:

```bash
omw vault use <name>
```

3. Confirm: "Active vault: `<name>` (`<mode>`, `<type>`) at `<path>`."

## Error handling

- Unknown name → registry raises ValueError. Re-list and re-prompt.
