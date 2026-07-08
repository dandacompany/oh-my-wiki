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
   `derived-from: [<source slug>]` in frontmatter; keep the source's citations). Use
   the normal page-writing path (`omw edit`/create flow) with `type: summary`, then
   `omw reindex`.

## After

Run `omw next --after summary --json` and offer the next lifecycle step (synthesis)
via the host's native ask tool — safe default: stop.
