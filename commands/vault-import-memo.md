# `vault-import-memo` — import an existing memo folder

Create or select the destination vault with `omw vault create` / `omw vault use`,
then preserve the source corpus with:

```bash
omw import --source folder --src-dir <path> --layer raw --vault <name>
```

Run `omw lint` after import. Any frontmatter normalization is proposed as a
separate, backed-up edit and applied only after explicit confirmation.
