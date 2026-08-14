# `vault-forget <name>` — remove a vault from the registry (files untouched)

**Underlying script:** `scripts.registry.forget_vault`

## Flow

1. Look up the vault to show its path. Refuse if the name is unknown.

2. **Explicit confirm** with the exact wording (this is a state change, even though files are preserved):

   > "Remove `<name>` from the registry? Files at `<path>` will NOT be deleted. Type the name to confirm."

   Require the user to type back the name. If they pick "Cancel" or mistype, abort.

3. Run:

```bash
omw vault forget <name>
```

4. Confirm: "Removed `<name>` from registry. Files at `<path>` are preserved."

## Error handling

- Unknown name → tell the user; abort.
- Removed vault was active → next command will report `no active vault`. Suggest `vault-use`.
