# `query` — ask the wiki

**Mode:** memo or wiki (search works for both)

## Preconditions

Active vault must exist.

## Flow

1. **Take a query string from the user.**

2. **Retrieve cited context.**

   ```bash
   omw context "<query>"
   ```

   This returns a JSON bundle with keys:
   - `query` — the original query string
   - `strategy` — the retrieval strategy used (`fts`, `embedding`, `hybrid`, or `llm`)
   - `hits` — list of `{slug, relpath, title, score, body, truncated, body_missing}` objects
   - `citations` — list of `{slug, title, relpath}` objects (deduplicated manifest)

   A `truncated: true` hit means the page body was capped at 4 000 characters; narrow the query to retrieve the full relevant passage.

   Skip any hit with `body_missing: true` when citing (its page is indexed but missing on disk).

3. **Synthesize the answer.**

   Using ONLY the `hits[].body` text returned, write a prose answer to the user's question.
   - Cite ONLY slugs present in `citations` as `[[slug]]` inline.
   - Do NOT invent citations or paraphrase from memory — every factual claim must be traceable to a hit body.
   - If the bodies do not answer the question, say so explicitly rather than improvising.

4. **Present the answer.** Show the synthesized prose + the citation list (formatted from `citations`).

5. **Offer to file the answer back** (wiki-mode only). Ask: "File this as a new synthesis page? [Yes / No]". If Yes:

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import query, ingest, registry
   db = registry_path()
   vault = registry.get_active(db)
   rel = query.write_synthesis(
       db, vault_id=vault['id'],
       title='<synthesis title>',
       body='<answer body, lightly edited for standalone reading>',
       citations=['<rel1>', '<rel2>'],
       tags=['<t1>','<t2>'],
       date_str='2026-05-25',
   )
   ingest.update_index(
       db, vault_id=vault['id'],
       entries=[('syntheses', '<slug>', '<oneliner>')],
   )
   ingest.append_log(
       db, vault_id=vault['id'],
       op='synthesis', title='<synthesis title>', date_str='2026-05-25',
   )
   print(rel)
   "
   ```

6. **Reindex** if a synthesis was filed:

   ```bash
   python3 -c "
   from scripts.paths import registry_path
   from scripts import reindex, registry
   db = registry_path()
   vault = registry.get_active(db)
   reindex.incremental(db, vault_id=vault['id'])
   "
   ```

## Post-conditions

- Read-only unless the user opted to file a synthesis.
- If filed: new page under `wiki/syntheses/`, updated `wiki/index.md` and `wiki/log.md`.

## Error handling

- Zero hits → suggest relaxing terms or running `omw lint` (index drift).
- Memo-mode vault → file-back is wiki-only; still show the answer + citations.
