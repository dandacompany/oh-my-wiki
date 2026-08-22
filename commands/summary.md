# `summary` — condense a page or source into a summary page

**Mode:** wiki (memo: just write a short note)

Produce a compact abstract of ONE existing page or source as a `summary`-type page
(schema `summary` = base). Distinct from `ingest` (which files a raw source and builds
entity/concept pages) and `synthesis` (which weaves MANY pages): summary is a TL;DR of
a single item.

## Preconditions

Active vault. The `page` arg names an existing page (relpath/slug) or a raw source.

## Flow

1. **Load the target.** `omw open <page>` (or read the raw/ file) to get its content
   and citations.

2. **Condense.** Write a faithful, standalone abstract — key claims only, no new facts,
   no invented detail. Keep the source's citations.

3. **Propose, then confirm** (never write silently). Show the draft. Ask:
   "File this as a summary page? [Yes / No]".

4. **On Yes, file it** as a `summary`-type page linked back to the source (set
   `derived-from: [<source slug>]` in frontmatter; keep the source's citations):

   ```bash
   omw page write --layer summaries --title "<title>" --body-file <body.md> \
     --tags <t1>,<t2> --date <YYYY-MM-DD> --source-raw <source-relpath> \
     --index "<oneliner>" --log-op summary
   ```

   `source_raw` is required on `summary` pages — a summary whose source cannot be
   traced is a schema violation, not a stylistic gap. `omw page write` reindexes.

## After

Run `omw next --after summary --json` and offer the next lifecycle step (synthesis)
via the host's native ask tool — safe default: stop.
