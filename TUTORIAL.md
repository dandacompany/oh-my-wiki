# oh-my-wiki — v3 Scenario Tutorial

> **Korean version**: [TUTORIAL.ko.md](./TUTORIAL.ko.md)

This tutorial walks you through building and maintaining a real wiki vault.
Every command block shows exact output from a live v3 CLI run.
Natural-language operations (ingest, query, autoresearch, personas) are shown
as prompts you say in a Claude Code / Codex / Gemini session — not as CLI output.

---

## Part 1 — What & why

**oh-my-wiki** is a wiki convention and maintenance framework you drive from
your AI coding agent. It implements the workflow Andrej Karpathy described in
his "LLM Wiki" Gist: every source becomes a raw snapshot, a summary page, and
10–15 entity and concept page touches. Queries pull from this structured wiki
rather than a flat file dump, so answers can cite specific pages.

### Host-universal

oh-my-wiki is **not tied to any specific AI host**. It runs identically in:

- **Claude Code** — SKILL.md is auto-discovered; trigger phrases fire the skill.
- **Codex CLI** — same SKILL.md, same trigger phrases.
- **OpenCode** — reads the same `AGENTS.md` convention as Codex.
- **Gemini CLI** — same SKILL.md, same trigger phrases.
- **Hermes** — runs per-profile (`~/.hermes/profiles/<profile>/`).
- **OpenClaw** — runs per-workspace.

No host is privileged. Whichever agent you are using today will work.

### Two-surface model

oh-my-wiki exposes exactly two surfaces:

| Surface         | What it is                                  | Examples                                                                                                                                             |
| --------------- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`omw` CLI**   | Deterministic ops — no LLM needed           | `omw status`, `omw vault create`, `omw lint`, `omw schema list`, `omw supersede`, `omw review`, `omw links`, `omw fields`, `omw setup`, `omw doctor` |
| **`omw` skill** | Natural-language reasoning inside a session | ingest, query, autoresearch, personas, find, edit, move, delete                                                                                      |

The model is: **personas propose → you confirm → deterministic ops execute**.
Writing personas analyze your content and suggest changes; the `omw` CLI writes
the deterministic output (linking, superseding, lint fixes). This keeps the
reasoning transparent and the file changes auditable.

---

## Part 2 — Install

Choose whichever path fits your environment. After the PyPI or git path, run
`omw doctor` to confirm everything is wired correctly. After the Skills CLI
path, the CLI is set up on first use (then `omw doctor`).

### Path A — PyPI (`pip` / `pipx`) — recommended

Install the `omw` CLI from [PyPI](https://pypi.org/project/oh-my-wiki/) without
cloning the repo:

```bash
pipx install oh-my-wiki        # isolated CLI (recommended)
# or
pip install oh-my-wiki         # into the current environment
```

The published wheel is self-contained — it bundles the schemas, personas,
backends, and the full skill — so you get a working `omw` immediately. To
register the bundled skill with your agents afterwards, run `omw setup agents`.
Installing straight from GitHub works the same way:
`pipx install git+https://github.com/dandacompany/oh-my-wiki`.

### Path B — git clone + install script (developers, Codex CLI users)

```bash
git clone https://github.com/dandacompany/oh-my-wiki
cd oh-my-wiki
bash bin/install.sh
```

The installer:

1. Checks for Python 3.10+.
2. Runs `pip install -e "."` (add `--dev` to include pytest/ruff for development).
3. Creates `~/.claude/skills/oh-my-wiki` and `~/.claude/skills/omw` symlinks (idempotent).
4. Runs `pytest -q` to verify the install on your machine (skip with `--no-test`).
5. Prints next steps and trigger phrases.

It is safe to re-run. Use `--force` to replace existing symlinks without a
prompt. Run `bash bin/install.sh --help` for all flags.

### Path C — Skills CLI (Claude Code users)

```bash
skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code
```

This installs the skill into `~/.claude/skills/` and registers both the
`oh-my-wiki` and `omw` short-alias skill names. This installs the skill only.
The `omw` CLI is installed on first use — open your agent and say
**`set up omw`** (or `omw 셋업 점검해줘`); the skill runs its CLI preflight
and installs the CLI with your confirmation. Or install it yourself now:
`pipx install oh-my-wiki`.

### Verify the install

```
omw doctor
```

Example output after a vault exists (paths will reflect your machine):

```
omw home:   /Users/you/.omw  ok
registry:   /Users/you/.omw/registry.db  ok
  * demo (wiki/markdown) /Users/you/.omw/vaults/demo
```

On a **fresh machine** before `omw setup` has been run, `doctor` prints:

```
omw home:   /Users/you/.omw  missing (run: omw setup)
registry:   /Users/you/.omw/registry.db  missing
  no vaults registered — run: omw setup
```

`doctor` reports `ok` for each component it finds, or explains what is missing.

---

## Part 3 — 5-minute quickstart

### Step 1 — Run the setup wizard

```
omw setup
```

`omw setup` is an interactive wizard that configures your first vault, search
provider, serve API, personas, import, viewer, agents, and per-prompt recall.
Follow the prompts. For a quick start, accept the defaults — you can always
re-run `omw setup vault` or `omw setup personas` later to adjust individual
sections.

### Step 2 — Check status

After setup, a fresh installation looks like this:

```
omw status
```

```json
{
  "vault_count": 0,
  "active": null,
  "needs": "setup",
  "vaults": []
}
```

`needs: "setup"` is what a real end-user sees on a clean machine. (If you are
running from the source tree, `data/registry.db` is present in the repo and
`needs` will show `"migrate"` instead — this is expected in the dev tree only.)

### Step 3 — Create your first vault

```
omw vault create demo --mode wiki
```

```json
{
  "created": "demo",
  "path": "~/.omw/vaults/demo",
  "mode": "wiki",
  "type": "markdown"
}
```

Confirm it is active:

```
omw vault list
```

```json
[
  {
    "name": "demo",
    "path": "~/.omw/vaults/demo",
    "mode": "wiki",
    "type": "markdown",
    "is_active": true
  }
]
```

### Step 4 — Add a note (in your AI session)

Open Claude Code (or Codex / Gemini) and say:

```
ingest this

Andrej Karpathy calls the LLM Wiki a "compounding knowledge artifact". Every
source gets saved verbatim to raw/, a summary lands at wiki/summaries/, and
the entities and concepts that appeared get their own pages. 10–15 page touches
per ingest is normal.
```

The skill will propose a title, slug, tags, and destination — confirm to save.

### Step 5 — Run a lint check

```
omw lint
```

On a clean vault with no issues:

```json
{
  "vault_id": 1,
  "vault_path": "~/.omw/vaults/demo",
  "frontmatter_issues": [],
  "drift": { "missing_files": [], "mtime_drift": [] },
  "links": {
    "broken": [],
    "orphans": [],
    "index_drift": { "missing_from_index": [], "dangling_in_index": [] },
    "contradictions": [],
    "supersedes": [],
    "superseded_unmarked": [],
    "link_suggestions": []
  },
  "auto_fix_hints": []
}
```

`frontmatter_issues: []` means every page passes the required-field check.
The `links` keys (`broken`, `orphans`, `index_drift`, `contradictions`,
`supersedes`, `superseded_unmarked`, `link_suggestions`) tell you the full
structural health of the vault. `drift` reports files present on disk but
missing from the index, and `auto_fix_hints` lists actionable remedies when
issues are found.

---

## Part 4 — Scenario: grow a real wiki

This section walks through a single continuous example. We use a `demo` vault
with three pages:

- `wiki/entities/andrej-karpathy.md` — entity page for Andrej Karpathy
- `wiki/concepts/llm-wiki.md` — concept page for the LLM Wiki method
- `wiki/concepts/old-method.md` — an older page we will retire

The vault was created in Part 3. The pages are added through the ingest
workflow (shown as in-session prompts below).

### 4.1 Schemas — what fields does each page type require?

oh-my-wiki ships 13 built-in page types. List them:

```
omw schema list
```

The 13 types are:
`article, book, comparison, concept, doc, entity, link, meta, note, paper, summary, synthesis, video`

Each entry in the list is a schema object with `type`, `required_fields`,
`required_sections`, `field_types`, and `allowed_values`. Inspect the entity
type in detail:

```
omw schema show entity
```

```json
{
  "type": "entity",
  "required_fields": ["title", "date", "type", "tags"],
  "required_sections": ["## Summary"],
  "field_types": {
    "tags": "list",
    "title": "str",
    "date": "str",
    "review": "dict",
    "aliases": "list"
  },
  "allowed_values": {
    "confidence": ["high", "medium", "low"],
    "status": ["draft", "inbox", "processed", "raw", "superseded", "meta"]
  }
}
```

Every entity page must have a `## Summary` section in its body. The
`confidence` field accepts `high`, `medium`, or `low`. The `status` field
accepts the values listed under `allowed_values`.

#### Per-vault schema overrides

You can override or extend any schema for a specific vault by creating a
`schemas/` folder inside the vault directory. Files in `<vault>/schemas/`
take precedence over the built-in `schemas/` at the package root. This lets
you add custom types or tighten field rules for a particular project without
touching the shared defaults.

```
~/.omw/vaults/demo/
└── schemas/
    └── entity.yml   ← overrides the built-in entity schema for this vault only
```

`omw schema show entity` will reflect the override when the `demo` vault is
active.

### 4.2 Ingest the demo pages

In your Claude Code (or Codex / Gemini) session, say:

```
ingest this

Andrej Karpathy is a researcher and educator known for karpathy.ai and the
LLM Wiki Gist. He describes wikis as compounding knowledge artifacts where
every source feeds the graph.
```

Confirm the proposed metadata. The skill writes `wiki/entities/andrej-karpathy.md`.

Then:

```
ingest this

The LLM Wiki method is a structured approach to personal knowledge management.
Raw sources go to raw/, processed pages go to wiki/. Andrej Karpathy popularized
this pattern. The owner field tracks who maintains the page.
owner:: dante
status:: draft
```

This writes `wiki/concepts/llm-wiki.md`. Notice the `owner:: dante` and
`status:: draft` lines — these are inline `key:: value` fields (Dataview
syntax). oh-my-wiki preserves and indexes them alongside frontmatter fields.

Then add the page you will later retire:

```
ingest this

The old flat-notes method stores everything in a single folder with no
structure. It is quick to start but does not scale.
```

This writes `wiki/concepts/old-method.md`.

### 4.3 Confidence and supersession

Pages carry a `confidence` field (`high`, `medium`, `low`) that signals how
well-sourced the page is. When a page is replaced by a better one, you mark it
`superseded` rather than deleting it — this preserves the audit trail.

Mark `old-method.md` as superseded by `llm-wiki`:

```
omw supersede wiki/concepts/old-method.md --by llm-wiki
```

```json
{
  "relpath": "wiki/concepts/old-method.md",
  "status": "superseded",
  "superseded_by": "llm-wiki"
}
```

oh-my-wiki writes two frontmatter fields to `old-method.md`:

```yaml
status: superseded
superseded_by: llm-wiki
```

`omw lint` will surface any pages that have been informally described as
"outdated" or "replaced" in their body but are missing these fields, under the
`superseded_unmarked` key.

### 4.4 Review cadence — spaced-repetition for wiki pages

Every page can carry a `review:` block in its frontmatter that schedules when
it should next be re-evaluated. The interval depends on confidence:

- `confidence: high` → 90-day interval
- `confidence: medium` → 30-day interval
- `confidence: low` → 7-day interval

Mark a review as done for `llm-wiki.md` (a high-confidence page):

```
omw review done wiki/concepts/llm-wiki.md --grade pass --today 2026-06-01
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "review": { "last": "2026-06-01", "due": "2026-08-30", "interval_days": 90 }
}
```

`high` confidence → 90-day interval → due date `2026-08-30`.

Query what is due for review (simulating a future date):

```
omw review due --today 2026-09-01
```

Returns a list of `{relpath, due, interval_days, confidence}` entries. Pages
with no `review:` block have `due: null` and sort first — they have never been
reviewed and deserve attention.

### 4.5 Web search, vault FTS5, and the local query API

#### `omw search` — external web search

`omw search "<query>"` performs a **web search** via an external provider
(brave / tavily / exa / firecrawl / brightdata). It pulls results from the
open web for research — it is **not** a search of your vault.

Configure a provider first:

```
omw setup search
```

Without a configured provider the CLI prints:

```
error: no search provider configured — run `omw setup search`
```

#### Searching your vault — FTS5 + in-session query

Your vault is indexed with **SQLite FTS5** (BM25 over title + summary + tags +
body), with an automatic token-scorer fallback. To search it:

- **In a Claude / Codex / Gemini session**: say "what does my wiki say about X"
  — the skill retrieves via FTS5 and LLM-reranks the results.
- **Via the local HTTP API** (`omw serve`): POST a query and get ranked hits as
  JSON (retrieve-only — no LLM in the server).

#### `omw serve` — local retrieve-only HTTP API

First generate an auth token (stored as `OMW_SERVE_TOKEN` in `~/.omw/.env`):

```
omw setup serve --generate-token
```

Then start the server:

```
omw serve
```

The server listens on **`http://127.0.0.1:8765`** (localhost only).
Query your vault with a `POST /query` (auth required) or check liveness with
`GET /health` (no auth). A `GET /query` returns 405.

```bash
# health (no auth)
curl -s http://127.0.0.1:8765/health

# query (POST + bearer token)
curl -s -X POST http://127.0.0.1:8765/query \
  -H "Authorization: Bearer $OMW_SERVE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "compounding knowledge", "limit": 5}'
```

See `references/messenger-api.md` for the full request/response JSON shape and
adapter sketches for Slack, Telegram, and Discord.

### 4.6 Entity auto-linking

As your wiki grows, you will mention entities in concept pages without linking
to them. oh-my-wiki detects these unlinked mentions and can insert the links
for you.

After adding the `llm-wiki.md` page (which mentions "Andrej Karpathy"), run:

```
omw links suggest
```

```json
[
  {
    "src_relpath": "wiki/concepts/llm-wiki.md",
    "target_slug": "andrej-karpathy",
    "target_relpath": "wiki/entities/andrej-karpathy.md",
    "mention": "Andrej Karpathy",
    "position": 145
  },
  {
    "src_relpath": "wiki/entities/andrej-karpathy.md",
    "target_slug": "llm-wiki",
    "target_relpath": "wiki/concepts/llm-wiki.md",
    "mention": "LLM Wiki",
    "position": 88
  }
]
```

The output lists every unlinked mention across all pages. Here `llm-wiki.md`
at character position 145 mentions "Andrej Karpathy" without a wikilink, and
`andrej-karpathy.md` at position 88 mentions "LLM Wiki" without a wikilink.
Both have matching pages in the vault.

Insert the link:

```
omw links link wiki/concepts/llm-wiki.md --to andrej-karpathy
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "target_slug": "andrej-karpathy",
  "mention": "Andrej Karpathy",
  "inserted": "[[andrej-karpathy|Andrej Karpathy]]"
}
```

oh-my-wiki rewrites the mention in place as `[[andrej-karpathy|Andrej Karpathy]]`.

#### Korean entity matching

oh-my-wiki handles Korean morphology correctly. If a page says:

```
안드레이 카르파시가 이 방법을 제안했다.
```

The josa `가` is attached to the entity name. `omw links suggest` detects that
`안드레이 카르파시가` matches the entity page slug for `안드레이 카르파시`,
and `omw links link` inserts:

```
[[…|안드레이 카르파시]]가 이 방법을 제안했다.
```

The josa is kept outside the wikilink bracket — the linked display text is the
canonical name without the josa.

#### Aliases

An entity page may declare an `aliases:` list in frontmatter:

```yaml
aliases:
  - Karpathy
  - AK
```

`omw links suggest` matches any alias against unlinked mentions, so you can
catch shorthand references as well as the full name.

### 4.7 Inline `key:: value` fields

Pages may carry inline Dataview-style fields in their body:

```
owner:: dante
status:: draft
uses:: [[llm-wiki]]
```

These are parsed and stored alongside frontmatter. Inspect a page's complete
field set:

```
omw fields wiki/concepts/llm-wiki.md
```

```json
{
  "relpath": "wiki/concepts/llm-wiki.md",
  "frontmatter": {
    "title": "LLM Wiki",
    "date": "2026-06-01",
    "type": "concept",
    "tags": ["method"]
  },
  "inline": { "owner": ["dante"], "status": ["draft"] }
}
```

Relation keys (`uses`, `contradicts`, `supersedes`) that reference wikilinks
(`[[other-page]]`) feed the typed-edge graph the same way that frontmatter
`relations:` does.

### 4.8 Wiki-maintenance personas (in-session, natural language)

oh-my-wiki ships five wiki-maintenance personas you invoke in your Claude Code /
Codex / Gemini session by talking naturally. No separate command is needed — the
skill routes to the right persona based on what you say. The roster is
wiki-librarian / curator / fact-checker / consistency-checker /
terminology-manager (see the Part 5 table).

**Curator** — reviews the wiki for gaps, orphan pages, and structural
weaknesses, then proposes a maintenance plan. In your Claude session, say:

```
curate my wiki — what pages are most in need of attention?
```

**Fact-checker** — decomposes a draft into atomic claims, verifies each via web
search, and writes a sibling report at `<your-page>.factcheck.md` with a
verdict table (supported / contradicted / partial / unverifiable). In your
Claude session, say:

```
fact-check wiki/concepts/llm-wiki.md
```

**Consistency-checker** — runs a full consistency pass: contradictions,
terminology drift, stale claims. In your Claude session, say:

```
check my wiki for contradictions
```

**Terminology-manager** — builds and maintains a glossary for your vault. In
your Claude session, say:

```
build a glossary for my vault
```

For sourced research, use the `autoresearch` wiki op (see the FAQ): it
decomposes a question into claims, runs up to 3 rounds of Bright Data MCP
searches per claim, assigns confidence tags, then drafts a synthesis page at
`wiki/syntheses/` and asks before filing it.

All personas follow the **propose → confirm → execute** model. They read your
files, draft proposals, and show you what will change before writing anything.

### 4.9 Per-prompt recall — your wiki shows up when you need it

A wiki only pays off if it gets _used_. `recall` makes your AI agent consult the
active wiki automatically, the moment you ask a question — you don't have to
remember to run `omw find`.

Enable it (it's also a step in the full `omw setup`, or run it on its own):

```
omw setup recall
```

This sets a mode, writes a short guidance block into your host instruction files,
and wires each host's native hooks (`SessionStart` + `UserPromptSubmit`).
omw is host-neutral here: one engine, translated into each host's hook format.

Host choices group by **instruction file (convention)** — `claude` (CLAUDE.md) ·
`codex·opencode` (AGENTS.md, written once) · `gemini` (GEMINI.md) · `hermes`
(pick a profile → `~/.hermes/profiles/<profile>/SOUL.md`) · `openclaw` (pick a
workspace → `<workspace>/AGENTS.md`). Set the profile/workspace non-interactively
with `--profile` / `--workspace`. Native hooks are wired for Claude Code, Codex,
and Gemini only; OpenCode, Hermes, and OpenClaw get the guidance block only.

Two axes you can configure:

- `recall.mode` — _when_ it acts:
  - `auto` — the hook searches the active vault on every prompt and, when a page
    is relevant, injects an `<omw-recall>` block (title · path · tags · citations)
    for the agent to ground its answer on.
  - `advisory` — the hook still searches and injects a strong hit when one is
    found (score ≥ min_score); it falls back to a one-line nudge (suggesting
    `omw find`) only when no strong hit meets the threshold. (auto vs advisory
    differ mainly when there is no strong hit: auto stays silent, advisory nudges.)
  - `off` — disabled.
- `recall.strategy` — _how_ it retrieves:
  - `fts` — keyword + Korean-josa normalization (deterministic, default).
  - `embedding` — semantic vector search via sqlite-vec; set a provider with
    `omw setup recall --embed-provider openai` (or `fake`). Without a provider
    it falls back to keyword (FTS) results.
  - `hybrid` — RRF fusion of fts + embedding; without an embedding provider it
    is effectively FTS.
  - `llm` — agent-delegated: the recall hook emits an `<omw-recall>` instruction;
    the in-session agent does the retrieval. Submodes via `recall.llm.submode`:
    `route` (agent picks keyword vs semantic, then `omw find`) · `generative`
    (agent pulls candidates, reads them, keeps only genuinely relevant).
    Unknown strategies fall back to `fts`.

What you'll see — ask something whose topic is in the wiki (e.g. "compare ARIMA
and Prophet for demand forecasting") and the agent receives:

```
<omw-recall> 활성 omw 위키에 관련 페이지가 있습니다 — 답변의 근거/출처로 활용하세요:
- Demand Forecasting — `wiki/syntheses/demand-forecasting.md` [arima,prophet] (score 1.9)
</omw-recall>
```

so its answer cites your own vetted, sourced page instead of guessing.

> Recall quality rides on good `title` / `tags` / `summary` frontmatter — the FTS
> index ranks on those, not full body text. `autoresearch` fills `summary`
> automatically; add tags to important pages to make them easy to surface.

---

## Part 5 — Reference

### CLI subcommands

| Subcommand        | Surface | One-line description                                                                                                                                                                                                                                                                                                                   |
| ----------------- | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `omw status`      | CLI     | Show registry state: vault count, active vault, `needs` code                                                                                                                                                                                                                                                                           |
| `omw vault`       | CLI     | Vault management: `create` · `list [--all]` · `use` · `current` · `info` · `rename` · `move` · `set` · `archive`/`unarchive` · `delete` (soft default, `--hard --yes`) · `forget`                                                                                                                                                      |
| `omw lint`        | CLI     | Deterministic vault health check (frontmatter + links + drift)                                                                                                                                                                                                                                                                         |
| `omw search`      | CLI     | Web search via the configured external provider (brave/tavily/exa/…)                                                                                                                                                                                                                                                                   |
| `omw serve`       | CLI     | Start the local retrieve-only HTTP query API (port 8765)                                                                                                                                                                                                                                                                               |
| `omw schema`      | CLI     | Show page-type schemas: `list`, `show <type>`                                                                                                                                                                                                                                                                                          |
| `omw supersede`   | CLI     | Mark a page `status: superseded` + `superseded_by: <slug>`                                                                                                                                                                                                                                                                             |
| `omw review`      | CLI     | Spaced-repetition queue: `due`, `done`                                                                                                                                                                                                                                                                                                 |
| `omw links`       | CLI     | Entity auto-link: `suggest`, `link`                                                                                                                                                                                                                                                                                                    |
| `omw fields`      | CLI     | Show a page's frontmatter + inline `key:: value` fields                                                                                                                                                                                                                                                                                |
| `omw import`      | CLI     | Import a folder / Obsidian / Notion (pages + database rows) · scanned image PDFs fall back to OCR (`oh-my-wiki[ocr]` extra)                                                                                                                                                                                                            |
| `omw setup`       | CLI     | Interactive wizard: vault, search, serve, personas, import, viewer, agents, recall                                                                                                                                                                                                                                                     |
| `omw doctor`      | CLI     | Validate omw config + install health                                                                                                                                                                                                                                                                                                   |
| `omw connections` | CLI     | Community detection over the wiki link graph; surfaces communities, bridges (cross-community links), and hubs (pages spanning ≥2 communities). Read-only JSON.                                                                                                                                                                         |
| `omw maint`       | CLI     | Knowledge-maintenance status: `omw maint status [--vault] [--exit-code]` counts stale/expired pages + lint issues; prints a one-line nudge. `--exit-code` returns 1 when work is due (cron-friendly).                                                                                                                                  |
| `omw report`      | CLI     | One-screen status + health dashboard: all-vaults summary + active vault composition (layers/entities/concepts/syntheses/graph/tags/index/inbox/review) + health verdict (install + vault grade + next actions). Text by default, `--json` for the structured dict; read-only.                                                          |
| `omw help`        | CLI     | Lifecycle-grouped overview of every command (`omw -h` / `--help` show the same)                                                                                                                                                                                                                                                        |
| `omw version`     | CLI     | Print the installed omw version (`omw -v` / `--version` show the same)                                                                                                                                                                                                                                                                 |
| `omw update`      | CLI     | Env-aware self-upgrade (`--check` report only / `--yes` non-interactive / `--no-refresh`); never touches config or the vault                                                                                                                                                                                                           |
| `omw uninstall`   | CLI     | Reverse omw's host integration: strip the managed blocks, remove omw's hooks, delete the skill bundle (auto-detected). `--purge` also removes ~/.omw config + secrets + registry; `--vaults` deletes vault content (typed confirm); `--dry-run` previews. Never deletes vaults without `--vaults`; prints the `pip uninstall` command. |
| `omw inbox`       | CLI     | URL inbox queue: `add` / `add-feed` (queue all entry links from an RSS/Atom feed) / `list` / `remove` / `run` (batch fetch)                                                                                                                                                                                                            |
| `omw context`     | CLI     | Cited-context retrieval — runs the configured strategy, reads each hit's body, returns hits + citations as JSON (prevents citation hallucination)                                                                                                                                                                                      |
| `omw list`        | CLI     | Faceted page listing (JSON): `--tag` / `--type` / `--status` / `--layer` / `--visibility` (no LLM)                                                                                                                                                                                                                                     |
| `omw export`      | CLI     | Export a vault slice to a self-contained Markdown dir (or `--zip`) + `EXPORT_MANIFEST.md`; writes only outside the vault                                                                                                                                                                                                               |
| `omw merge`       | CLI     | Consolidate two near-duplicate pages into one (frontmatter union + `## Merged from` body + winner `aliases` + source tombstone); staged as `.proposed.md` → `--apply`                                                                                                                                                                  |

Reasoning-ops (`ingest`, `query`, `find`, `edit`, `autoresearch`, personas)
require a Claude / Codex / Gemini session — use them by speaking naturally in
your agent session. oh-my-wiki does not ship multi-step orchestration; your host
AI agent (Claude Code / Codex / Gemini) handles chaining these ops together.

### Frontmatter conventions

**Required fields** (all page types except `meta`):

```yaml
title: "Page Title"
date: "2026-06-01"
type: concept # one of the 13 schema types
tags: [method, wiki]
```

**Optional fields**:

```yaml
confidence: high # high | medium | low (drives review interval)
status: draft # draft | inbox | processed | raw | superseded | meta
superseded_by: llm-wiki # slug of the replacement page (when status: superseded)
review:
  last: "2026-06-01"
  due: "2026-08-30"
  interval_days: 90
aliases:
  - Karpathy LLM Wiki
  - LLM wiki method
```

**Inline fields** (in the body, Dataview syntax):

```
owner:: dante
status:: draft
uses:: [[llm-wiki]]
contradicts:: [[old-method]]
```

### Persona roster

| Persona                 | Invocation phrase             | Output                            |
| ----------------------- | ----------------------------- | --------------------------------- |
| **Wiki-librarian**      | "open my wiki", "ingest this" | Routes ingest / organize requests |
| **Curator**             | "curate my wiki"              | Maintenance proposal (in-session) |
| **Fact-checker**        | "fact-check this"             | `<page>.factcheck.md`             |
| **Consistency-checker** | "check for contradictions"    | JSON report (in-session)          |
| **Terminology-manager** | "build a glossary"            | `glossary.db`                     |

### Schema locations

- **Built-in schemas**: `schemas/<type>.yml` in the package root — 13 types.
- **Per-vault overrides**: `<vault>/schemas/<type>.yml` — takes precedence over built-in for that vault.

`omw schema show <type>` always reflects the active override if one exists.

### `OMW_HOME`

oh-my-wiki stores its registry at `$OMW_HOME/registry.db` (default:
`~/.omw/registry.db`). Override with the environment variable:

```bash
export OMW_HOME=/path/to/isolated/.omw
omw status
```

This is useful for testing, CI, or running a completely separate wiki
environment without touching your main registry.

---

## Part 6 — FAQ and troubleshooting

### Q. `omw doctor` says the registry is missing

This is normal on a brand-new install before running `omw setup`. Run:

```
omw setup
```

The wizard creates the registry and your first vault. After that, `omw doctor`
reports `ok`.

### Q. `omw status` shows `needs: "migrate"` instead of `needs: "setup"`

`needs: "migrate"` appears when `omw status` detects a legacy `data/registry.db`
file in the skill directory (or `<cwd>/data/registry.db`). This happens in a
**source-tree checkout** where `data/registry.db` is present on disk.

Real end-users who install via Skills CLI, PyPI (`pip`/`pipx`), or
`bin/install.sh` see `needs: "setup"` on a fresh machine — `data/` is gitignored
and not included in the distributed package.

> **Note:** Overriding `OMW_HOME` (e.g. `export OMW_HOME=$(mktemp -d)/.omw`)
> does **not** simulate a clean end-user environment when running from a source
> checkout. Legacy detection scans `<skill_dir>/data/registry.db` independently
> of `OMW_HOME`, so the mktemp trick still returns `needs: "migrate"` from a
> source tree.

The remedy in both cases is `omw setup` — the wizard migrates or initializes
the registry as appropriate.

### Q. oh-my-wiki did not auto-trigger in my session

Use an explicit trigger phrase:

- English: "open my wiki", "ingest this", "what does my wiki say about X", "omw", "/omw"
- Korean: "위키 열어줘", "이거 정리해줘", "위키에 물어봐", "오엠더블유"

Or just say: `use the oh-my-wiki skill`.

### Q. `omw search` returns an error / no provider configured

`omw search` is a **web search** command — it queries an external search
provider (brave, tavily, exa, firecrawl, or brightdata), not your vault.
If no provider is configured, you will see:

```
error: no search provider configured — run `omw setup search`
```

Run `omw setup search` and enter your provider credentials to fix this.

### Q. Vault FTS5 is unavailable / in-session query returns no results

Your vault index uses SQLite FTS5 (BM25) internally. oh-my-wiki falls back
to a token-scorer automatically when FTS5 is unavailable. Most modern Python
sqlite3 builds include FTS5. To check:

```bash
python3 -c "import sqlite3; c = sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(body)'); print('FTS5 ok')"
```

If that errors, your sqlite3 build lacks FTS5. Install a full-featured build:

```bash
# macOS with Homebrew
brew install sqlite
```

The fallback token-scorer still works — you will not lose results, just
BM25 ranking precision.

### Q. How do I isolate two separate wikis?

Use `OMW_HOME` to point each environment at its own registry:

```bash
export OMW_HOME=~/work/.omw   omw vault create work-notes --mode wiki
export OMW_HOME=~/personal/.omw   omw vault create journal --mode wiki
```

Each `OMW_HOME` has its own `registry.db` and `vaults/`. The vaults themselves
can live anywhere; the registry just records their paths.

### Q. What vault modes are available?

`omw setup vault` (and `omw vault create --mode`) accepts:

- **memo** — flat `inbox/` for quick capture
- **wiki** — Karpathy three-layer (`raw/` + `wiki/{summaries,entities,concepts,comparisons,syntheses}/`)
- **personal** — `journal/ goals/ people/ health/`
- **book** — `chapters/ characters/ worldbuilding/ outlines/ drafts/`
- **business** — `meetings/ decisions/ clients/ vendors/ processes/`
- **github-codebase** — `modules/ apis/ decisions/ runbooks/ glossary/`
- **website** — `pages/ posts/ assets/ seo/ outlines/`

Every mode also gets `.trash/` for soft deletes and an `index.md` (plus
`wiki/log.md` for wiki mode).

### Q. How does oh-my-wiki work in Codex CLI vs Claude Code?

Identically. SKILL.md is host-agnostic — the same trigger phrases, same
routing logic, and same commands work in any AI coding agent that discovers
the skill. Codex is sometimes more conservative about auto-triggering; if the
skill does not fire on a trigger phrase, say "use the oh-my-wiki skill" to
invoke it explicitly.

### Q. How does autoresearch work?

`autoresearch <your question>` runs up to 3 rounds (configurable; hard cap 5)
of:

1. Decompose the question into claims.
2. Search the web via Bright Data MCP per claim.
3. Tag each claim with high / medium / low confidence based on source quality.
4. Identify gaps and run another round if any remain.

When there are no remaining gaps (or the round budget is hit), the skill drafts
a synthesis and asks before filing it to `wiki/syntheses/<slug>.md`. The full
session — claims, sources, gaps per round — is preserved under
`<vault>/.oh-my-wiki/sessions/<ts>-<slug>/` for audit and replay.

### Q. How do I roll back a vault import?

`omw import` (and the older `vault-import-memo` flow) always backs up
pre-images to `.trash/<ts>-pre-import-*.md` before writing. To restore a
single file:

```bash
cp ~/.omw/vaults/legacy/.trash/20260601-pre-import-meeting-notes.md \
   ~/.omw/vaults/legacy/meeting-notes.md
```

To roll back the entire batch, restore every file with the same timestamp
prefix at once.

### Q. How does the hot cache / session continuity work?

Each session, oh-my-wiki reads a small `hot.md` cache file at session start
and refreshes it at session end so you don't have to recap context across
sessions:

- wiki-mode vaults: `<vault>/wiki/hot.md`
- memo-mode and other modes: `<vault>/hot.md`

Cap: 2000 characters. Manual refresh: `python3 -m scripts.hot_cache --refresh`.
Manual inspect: `python3 -m scripts.hot_cache --on-session-start`.

---

## More

- **Command reference**: `commands/*.md` covers every op.
- **Script API**: `scripts/*.py` is callable from Python; a subset is also exposed as CLI subcommands.
- **Design docs**: `docs/superpowers/specs/` (local-only, not published — for contributors).
- **Tests**: `pytest -v` runs the full test suite.

Issue tracker: https://github.com/dandacompany/oh-my-wiki/issues
