# `lint` — check vault health

Run `omw status` to confirm the active vault, then run `omw lint`. The JSON
contains common frontmatter/drift checks and, for wiki vaults, the structural
link/orphan/contradiction/staleness checks. This operation is read-only.

Autoresearch session state can be inspected with:

```bash
omw research status --session-dir <DIR>
```
