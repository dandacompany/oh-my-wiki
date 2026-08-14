# `autoresearch` — multi-round web research, raw-first

**Mode:** wiki (rejected on memo vaults)
**Underlying script:** `scripts.autoresearch` (subcommands: init / record / should-stop / status / file-back)
**Default contract:** collect useful sources into `raw/` first; synthesis into `wiki/syntheses/` is an **explicit user fork**, not automatic. With `--no-synthesis` the run is a hard stop _before_ any draft/file-back.

## Preconditions

Active vault must be wiki-mode. Run `omw status` first. If active vault is memo-mode, suggest `omw vault use <wiki-vault>` or `omw vault create`.

If `confirm_target` is `true` (2+ vaults registered), confirm the destination with the user before any file-back — "N개 vault 중 `<name>` (`<path>`)에 씁니다 — 진행할까요?" — unless this vault was already confirmed in this session (see SKILL.md Multi-vault write guard). (Collect-only / `--no-synthesis` runs write only to `raw/` and never trigger this.)

## Flow

### Step 1 — Initialize the session

Get the user's research question. Then:

```bash
omw research init \
  --query "<the user's question>"
```

Parse the JSON output:

```json
{
  "session_id": "20260526-204500-...",
  "session_dir": "/.../sessions/...",
  "max_rounds": 3
}
```

Tell the user: "Session started: <session_id>. Up to <max_rounds> rounds."

### Step 2 — Round loop

For `round_num` in 1, 2, ... up to `max_rounds`:

**(a) Decompose.** For round 1, break the original query into 3–6 atomic claims (testable statements). For round 2+, focus on `gaps_remaining` from the previous round.

**(b) Search.** **Search-first contract:** use `omw search "<claim or gap>" --limit 5` first. It auto-falls back across configured keyed providers and returns JSON with `results`, `provider`, and `tried`. Use host-native fetch/read (or Bright Data MCP `mcp__brightdata__search_engine` / `scrape_as_markdown`) only as an optional fallback for quick inspection or when no provider is configured — not as the primary path.

**(c) Fetch useful sources into `raw/`.** For each URL that should become part of the vault's raw layer, run:

```bash
omw fetch "<url>"
```

Parse its JSON output (`{text, title, backend, source_url, raw_relpath}`) and record `raw_relpath`, `title`, and `url` in the claim's `sources` list. Native/built-in fetch runs first; a cloud provider only backs hard-blocked pages (see `commands/fetch.md`). Do not hand-scrape search-engine HTML.

**(d) Read + judge.** For each claim, read the fetched sources and decide a confidence tag:

- **high** — multiple independent reputable sources agree
- **medium** — single strong source or multiple weak sources agreeing
- **low** — conflicting sources, weak source only, or no source found

**(e) Detect gaps.** Identify gaps that need another round (unresolved claims, follow-up questions raised by sources, contradictions to reconcile). Plain-English strings.

**(f) Record the round** — each source is an object carrying `url`/`title`/`raw_relpath` (a bare string still works and is normalized to `{"label": ...}`):

```bash
omw research record \
  --session-dir <session_dir> \
  --round <round_num> \
  --claims-json '[{"claim":"...","confidence":"high","sources":[{"url":"https://...","title":"...","raw_relpath":"raw/2026-06-29-...md"}]}, ...]' \
  --gaps-json '["...", "..."]' \
  --notes "<optional notes for self/next round>"
```

`confidence` must be one of `high|medium|low` (the recorder rejects anything else).

**(g) Check stop:**

```bash
omw research should-stop --session-dir <session_dir>
```

If `{"stop": true, ...}` → break loop. Otherwise continue to round_num+1.

### Step 3 — Decide output mode

Read the bound CLI card.

**If the card includes `no-synthesis: True` (mode: collect raw only):** STOP here. Do **not** compose a synthesis draft and do **not** call `file-back`. Report:

- session id
- rounds completed + stop reason (`should-stop` reason)
- raw files collected — the `raw_relpaths` from:

  ```bash
  omw research status --session-dir <session_dir>
  ```

- unresolved gaps, if any

That is the whole run — sources are now in `raw/` for later graph/connection/synthesis work.

**If `no-synthesis` is false or absent:** surface the synthesis fork as a **structured choice** (decision class `autoresearch-synthesize`; safe default first):

1. **Leave in raw** (safe default) — same report as the collect-only branch; stop.
2. **Synthesize into `wiki/syntheses/` now** → Step 4.
3. **Edit draft first** → compose, show, revise, then Step 4.

### Step 4 — Compose + file back (synthesis branch only)

Read all `round-*.json` files. Compose a synthesis page:

- **Title** — a short noun phrase summarizing the answer
- **Body** — ordered narrative answer with inline citations like `[per-claim summary](source-url)`; group claims by topic; flag any `low`-confidence claims as "uncertain"
- **Tags** — 2–5 nouns
- **Citations** — flat array of all source URLs used

Write the body to a temp file (avoids CLI length issues), then file back:

```bash
tmp_body=$(mktemp)
cat > "$tmp_body" <<'BODY'
<the synthesis body>
BODY

omw research file-back \
  --session-dir <session_dir> \
  --title "<synthesis title>" \
  --body-file "$tmp_body" \
  --citations-json '["url1", "url2", ...]' \
  --tags-json '["tag1", "tag2"]' \
  --date <YYYY-MM-DD>
```

Output is the synthesis page relpath (e.g. `wiki/syntheses/why-attention-beats-rnn.md`). Then incremental reindex so search picks it up:

```bash
omw reindex
```

### Step 5 — Report

- Collect-only: session id, rounds + stop reason, `raw_relpaths`, unresolved gaps.
- Synthesis: the synthesis page relpath, rounds + stop reason, confidence breakdown (high/medium/low counts), and optional next steps (`lint`, `find <topic>`, `connections`).

## Post-conditions

**Always:** fetched sources saved under `raw/<date>-<slug>.md`; session dir at `.oh-my-wiki/sessions/<session_id>/` with `mission.json` + `round-*.json` (replayable audit trail; round JSON records normalized sources with `raw_relpath`).

**Synthesis branch only:** a new `wiki/syntheses/<slug>.md` (`type: synthesis`, `citations: [...]`); `wiki/index.md` updated under `## Syntheses`; `wiki/log.md` appended with `## [YYYY-MM-DD] autoresearch | <title>`; `filed.json` in the session dir.

## Error handling

- Active vault is memo-mode → init raises `VaultError`. Suggest `vault-use <wiki-vault>` or `vault-setup`.
- No search provider configured and Bright Data MCP unavailable → ask the user to paste source content per claim, or run `omw setup search`.
- Invalid `confidence` (not high/medium/low) → `record` raises `ValueError`; fix the tag and re-record (idempotent overwrite).
- `--no-synthesis` bound → never call `file-back`; the run ends at the Step 3 collect-only report.
- File-back called twice on the same session → idempotent; returns the prior relpath without re-writing.

## Ask (omw-ask)

This op's user fork is decision class `autoresearch-synthesize`. Surface it as a **structured choice** per the omw-ask convention (see SKILL.md + the `omw-ask` managed block) with the safe default **Leave in raw** offered first; honor the session-sticky and non-interactive degrade rules. When `--no-synthesis` is bound there is **no fork** — the run is collect-only and stops before synthesis.
