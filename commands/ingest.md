# `ingest` — capture a source into the wiki

**Mode:** wiki (active vault must be wiki-mode)
**Underlying scripts:** `scripts.ingest.save_raw` / `save_raw_pdf` / `write_wiki_page` / `update_index` / `append_log`; `scripts.reindex.incremental`

## Preconditions

Call `python3 -m scripts.wizard status` first. Refuse if `active.mode != "wiki"`. Suggest `vault-use <wiki-vault>` or `vault-setup` if not.

## Input branches

Detect the source type from user input:

| User input                  | Branch            | Extraction                                                                                                                                                                 |
| --------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pasted long-form text       | paste             | use as body                                                                                                                                                                |
| Path ending in `.pdf`       | pdf file          | `ingest.save_raw_pdf` → returns (relpath, extracted_text)                                                                                                                  |
| Path ending in `.md`/`.txt` | text file         | `Path(p).read_text()` → body                                                                                                                                               |
| URL                         | `omw fetch <url>` | runs the deterministic fetch cascade (yt-dlp/urllib/chromium/cloud) → saves raw/, returns the relpath; then continue from step 2 (Discuss takeaways) reading that raw file |

For a URL, prefer `omw fetch <url>` (deterministic, handles YouTube + SPA) over an ad-hoc MCP fetch; it saves the source to `raw/` and you continue the synthesis steps below against that file.

For paste/md/txt, use `ingest.save_raw` with `ext` = `md` or `txt`. For pdf, use `ingest.save_raw_pdf` (returns extracted text for the next step).

## Flow

1. **Save the raw source.**

   For paste/md/txt:

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   rel = ingest.save_raw(
       db, vault_id=vault['id'],
       content='''<body>''',
       ext='md', title='<title>', date_str='2026-05-25',
   )
   print(rel)
   "
   ```

   For PDF (body is bytes — use stdin or a temp file):

   ```bash
   python3 -c "
   import sys
   from pathlib import Path
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   pdf_bytes = Path('<input.pdf>').read_bytes()
   rel, text = ingest.save_raw_pdf(
       db, vault_id=vault['id'],
       pdf_bytes=pdf_bytes,
       title='<title>', date_str='2026-05-25',
   )
   print(rel)
   print('---EXTRACTED---')
   print(text)
   "
   ```

2. **Discuss takeaways with the user.** Read the body. Propose: a one-paragraph summary, 2-5 key entities (people, orgs, papers), and 2-5 key concepts (ideas, techniques). Show the proposal and get the user's confirmation.

3. **Write the summary page.**

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   rel = ingest.write_wiki_page(
       db, vault_id=vault['id'],
       layer='summaries',
       title='<source title>',
       body='<summary body>',
       tags=['<t1>','<t2>'],
       date_str='2026-05-25',
   )
   print(rel)
   "
   ```

4. **Write entity / concept pages.** For each new entity:

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   rel = ingest.write_wiki_page(
       db, vault_id=vault['id'],
       layer='entities',
       title='<entity name>',
       body='<one-paragraph description>',
       tags=['person'],
       date_str='2026-05-25',
   )
   print(rel)
   "
   ```

   For an existing entity that needs patching, use `scripts.frontmatter.edit_field` for metadata or rewrite the body via standard file write. Then call `reindex.incremental`.

5. **Update the index.** Aggregate all touched (layer, slug, oneliner) entries:

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   ingest.update_index(
       db, vault_id=vault['id'],
       entries=[
           ('summaries', '<slug>', '<oneliner>'),
           ('entities', '<slug>', '<oneliner>'),
           ('concepts', '<slug>', '<oneliner>'),
       ],
   )
   "
   ```

6. **Append to the log.**

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   ingest.append_log(
       db, vault_id=vault['id'],
       op='ingest', title='<source title>', date_str='2026-05-25',
   )
   "
   ```

7. **Reindex.**

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import reindex, registry
   db = registry_path()
   vault = registry.get_active(db)
   reindex.incremental(db, vault_id=vault['id'])
   "
   ```

8. **Report** to the user: raw relpath, summary relpath, list of entity/concept relpaths touched (10-15 page touches per ingest is normal — Karpathy convention).

## Error handling

- Active vault is memo-mode → refuse, suggest `vault-use`.
- PDF extraction empty → continue, but warn the user the PDF may be scanned (no OCR in Plan C); body stays empty, user can paste manually.
- File not found → re-prompt for path or paste.
- Index update on a layer without a section → `ingest.update_index` creates it automatically; mention this in the report.
