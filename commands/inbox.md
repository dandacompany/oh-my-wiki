# `inbox` — queue URLs and batch-fetch them into raw/

**Mode:** wiki. **Underlying:** `omw inbox add|list|run|remove`, `omw fetch <url>` (deterministic CLI).

## When to use

The user drops one or more URLs (articles, papers, YouTube links) to capture later, or says "process my inbox". Fetching is deterministic (no LLM); summary/entity synthesis happens afterward via the normal `ingest` flow.

## Flow

1. **Add** each URL: `omw inbox add <url>` (dedups the queue by normalized URL; YouTube canonicalized by video id).
2. **Review** the queue: `omw inbox list`.
3. **Run** the batch: `omw inbox run` first checks `raw/` frontmatter for a matching normalized `source_url`. Existing sources are reused without a network call or `-N.md` copy; new sources are fetched, saved with URL provenance, and marked `fetched`/`failed`. Report `{fetched, deduped, failed}`.
4. For each `failed` item, read the `error`:
   - `yt-dlp is not installed` → tell the user yt-dlp is required for YouTube; offer to install (`pip install yt-dlp` or `brew install yt-dlp`). Only install on explicit consent, then re-run.
   - `playwright/chromium is not installed` (SPA page) → recommend `omw setup playwright` (env-aware install), OR suggest `omw inbox run --backend cloud` if a Firecrawl/Bright Data key is configured (`omw setup search`).
   - `blocked URL` → SSRF guard; the URL targets a local/private host. Skip it.
5. After `run`, the new `raw/` docs are ready. Offer to **ingest** them (summary + entities + concepts) via the normal `ingest` procedure — one raw doc at a time, propose→confirm as usual.

## Feed ingestion

`omw inbox add-feed <feed-url>` parses an RSS/Atom feed and queues every entry link (then `omw inbox run`).

## Single URL

For a one-off, `omw fetch <url>` fetches + saves raw immediately (no queue), then run `ingest` on it.
