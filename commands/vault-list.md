# `vault-list` — show all registered vaults

**Underlying script:** `scripts.registry.list_vaults` (+ per-vault note counts)

## Flow

1. Run:

```bash
omw vault list
```

2. Render to the user. The `*` marks the active vault.

## Post-conditions

- Read-only.

## Error handling

- No vaults registered → tell the user to run `vault-setup` or `vault-import-memo`.
