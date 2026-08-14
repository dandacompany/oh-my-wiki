# `vault-setup` — register a new vault

Use the public CLI only:

```bash
omw vault create <name> --mode <mode> --type <markdown|obsidian> \
  [--location global|project|custom] [--path <absolute-path>]
```

Show the proposed name, location, mode, and type before creation. Confirm the
active vault afterward with `omw status`.
