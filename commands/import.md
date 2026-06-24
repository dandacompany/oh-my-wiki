# import

Bulk-import an external corpus (folder / Obsidian vault / Notion) into the active
omw vault. Deterministic copy via `omw import`; default layer `raw` (originals
preserved — promote later), `--layer wiki` writes pages with a minimal stub.

## When to invoke

"import my notes folder", "pull in my Obsidian vault", "import from Notion",
"노트 폴더 가져와줘", "옵시디언 가져오기".

## Procedure

1. **Confirm source + target.** Source = folder | obsidian | notion; target vault
   (active or `--vault`); layer (raw default).
2. **For notion**, ensure the key is set: `omw setup import` (interactive — prompts
   for the Notion integration token, stored in `~/.omw/.env`).
3. **Run the import:**
   ```bash
   omw import --source folder   --src-dir <path> [--layer raw|wiki] [--vault <name>]
   omw import --source obsidian --src-dir <vault-path> [--layer …]
   omw import --source notion   --notion-id <page-id> [--layer …]
   ```
   Reads JSON `{imported, skipped, source}`.
4. **Report** counts. For `--layer wiki`, optionally normalize frontmatter (propose
   better title/tags/type per page, then write + `python3 -m scripts.reindex --vault-id <id>`).

> **Note (Notion databases):** `child_database` blocks inside a Notion page are now
> imported automatically. Each row in the database is treated as a page and imported
> alongside child pages under `<layer>/import/notion/`. Pagination is handled
> transparently (100 rows per request).
