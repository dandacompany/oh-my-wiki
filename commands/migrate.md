# `migrate` — import a legacy registry into ~/.omw

**Trigger:** `wizard status` returned `needs == "migrate"`.

## Flow

1. Show the user the legacy location (`legacy_path`) and the vaults found
   (`vaults`: name + path), and the count (`legacy_vault_count`).

2. AskUserQuestion (2 options):
   - **Import to ~/.omw (recommended)** — copy the registry index. Vault content
     is untouched (paths are absolute and stay valid).
   - **Clean start** — ignore the legacy registry; proceed to `vault-setup`.

3. On **Import**, run:

   ```bash
   omw setup vault
   ```

   Then report the result (`vault_count`, new `registry` path). The legacy file
   is renamed to `registry.db.migrated` so this prompt does not repeat.

4. On **Clean start**: load `commands/vault-setup.md` (global default).

## Error handling

- Verification mismatch (copied row count != source) → `wizard migrate` raises and
  leaves the legacy intact. Report the error and stop; do not retry blindly.
- Destination already exists → `wizard migrate` refuses (raises) to avoid
  overwriting an existing registry. Report and stop.
