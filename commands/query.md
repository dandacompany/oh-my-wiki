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

   Save the approved answer to a UTF-8 file and run:

   ```bash
   omw page write --layer syntheses --title "<synthesis title>" --body-file <body.md> \
     --tags <t1>,<t2> --date <YYYY-MM-DD> --citation <rel1> --citation <rel2> \
     --index "<oneliner>" --log-op synthesis
   ```

6. **Reindex** if a synthesis was filed:

   `omw page write` reindexes automatically.

## Post-conditions

- Read-only unless the user opted to file a synthesis.
- If filed: new page under `wiki/syntheses/`, updated `wiki/index.md` and `wiki/log.md`.

## Error handling

- Zero hits → suggest relaxing terms or running `omw lint` (index drift).
- Memo-mode vault → file-back is wiki-only; still show the answer + citations.
