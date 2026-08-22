# `ingest` — capture a source into the wiki

**Mode:** wiki (active vault must be wiki-mode)
**Underlying scripts:** `scripts.ingest.save_raw` / `save_raw_pdf` / `write_wiki_page` / `update_index` / `append_log`; `scripts.reindex.incremental`

## Preconditions

Call `omw status` first. Refuse if `active.mode != "wiki"`. Suggest `omw vault use <wiki-vault>` or `omw vault create` if not.

If `confirm_target` is `true` (2+ vaults registered), confirm the destination with the user before writing — "N개 vault 중 `<name>` (`<path>`)에 씁니다 — 진행할까요?" — unless this vault was already confirmed in this session (see SKILL.md Multi-vault write guard).

## Input branches

Detect the source type from user input:

| User input                  | Branch            | Extraction                                                                                                                                                                 |
| --------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pasted long-form text       | paste             | use as body                                                                                                                                                                |
| Path ending in `.pdf`       | pdf file          | `ingest.save_raw_pdf` → returns (relpath, extracted_text)                                                                                                                  |
| Path ending in `.md`/`.txt` | text file         | `Path(p).read_text()` → body                                                                                                                                               |
| URL                         | `omw fetch <url>` | runs the deterministic fetch cascade (yt-dlp/urllib/chromium/cloud) → saves raw/, returns the relpath; then continue from step 2 (Discuss takeaways) reading that raw file |

For a URL, prefer `omw fetch <url>` (deterministic, handles YouTube + SPA) over an ad-hoc MCP fetch; it saves the source to `raw/` and you continue the synthesis steps below against that file. Try your native fetch first — only fall back to `omw fetch <url>` if native fetch returns empty or is blocked.

**Scout first:** If the target URL is unknown, run `omw search "<query>"` (auto-falls back across providers) to find candidate URLs, then collect them with `omw fetch` (native fetch first — see `commands/fetch.md`). Do not hand-scrape search-engine HTML.

For a local md/txt/pdf file, use `omw capture <path> --title "<title>" --date <YYYY-MM-DD>`.

## Flow

1. **Save the raw source.**

   Save pasted text to a temporary UTF-8 `.md` file, then run:

   ```bash
   omw capture <input.md|input.txt|input.pdf> --title "<title>" --date <YYYY-MM-DD>
   ```

2. **Discuss takeaways with the user.** Read the body. Propose: a one-paragraph summary, 2-5 key entities (people, orgs, papers), and 2-5 key concepts (ideas, techniques). Show the proposal and get the user's confirmation.

3. **Write the summary page.**

   Save the approved body to a temporary UTF-8 file, then run:

   ```bash
   omw page write --layer summaries --title "<source title>" --body-file <body.md> \
     --tags <t1>,<t2> --date <YYYY-MM-DD> --source-raw <raw-relpath> \
     --index "<oneliner>" --log-op ingest
   ```

   - **Provenance.** When you write a wiki page from a raw source, set
     `source_raw: [<raw relpath>]` in its frontmatter (a list — a synthesis may derive
     from several). This makes raw sources traceable from the wiki page.
   - **Relations.** Prefer the precise relation verbs in `relations:` —
     `derived-from`, `extends`, `illustrates`, `applies-to`, `instances-of`,
     `see-also`, `synthesizes` (alongside `uses`/`contradicts`/`supersedes`).
     Set them deterministically — the shape is a mapping of verb to targets:

     ```bash
     omw page write … --relation see-also=red-green-refactor --relation uses=fakes-over-mocks
     ```

     ```yaml
     relations:            # canonical shape written by --relation
       see-also: [red-green-refactor]
       uses: [fakes-over-mocks]
     ```

     The hand-written list form (`- see-also: slug`) is also read, but prefer the
     mapping. A
     `synthesis` page must set `synthesizes: [slugs]` + a `## Sources` section; a
     `comparison` must set `compared_items: [...]`.

4. **Write entity / concept pages.** For each new entity:

   ```bash
   omw page write --layer entities --title "<entity name>" --body-file <body.md> \
     --tags person --date <YYYY-MM-DD> --source-raw <raw-relpath> --index "<oneliner>"
   ```

   For an existing entity that needs patching, use `scripts.frontmatter.edit_field` for metadata or rewrite the body via standard file write. Then call `reindex.incremental`.

5. **Update the index.** Aggregate all touched (layer, slug, oneliner) entries:

   `omw page write --index "<oneliner>"` updates the matching section.

6. **Append to the log.**

   `omw page write --log-op ingest` appends the log entry.

7. **Reindex.**

   `omw page write` and `omw capture` reindex automatically. After any direct
   file edit, run `omw reindex`.

8. **Propose entity links.** Run `omw links suggest` (Korean-josa-aware). Show the user the suggested `[[slug]]` insertions for the pages just written and any prior pages that now mention the new entities. On confirmation, apply one with `omw links link <relpath> --to <slug>` or the confirmed set with `omw links link --from-suggestions`; the batch form reindexes once at the end. Never insert silently — keep the graph connected, but each applied set is a confirmed proposal.

9. **Report** to the user: raw relpath, summary relpath, list of entity/concept relpaths touched (10-15 page touches per ingest is normal — Karpathy convention).

## Error handling

- Active vault is memo-mode → refuse, suggest `vault-use`.
- PDF extraction empty → continue, but warn the user the PDF may be scanned (no OCR in Plan C); body stays empty, user can paste manually.
- File not found → re-prompt for path or paste.
- Index update on a layer without a section → `ingest.update_index` creates it automatically; mention this in the report.

## Ask (omw-ask)

This op's user fork is decision class `duplicate-ingest`. Surface it as a **structured choice** per the omw-ask convention (see SKILL.md + the `omw-ask` managed block) with the safe default **Skip** offered first; honor the session-sticky and non-interactive degrade rules.
