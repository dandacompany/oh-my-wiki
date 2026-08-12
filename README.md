# oh-my-wiki (OMW)

[![CI](https://github.com/dandacompany/oh-my-wiki/actions/workflows/ci.yml/badge.svg)](https://github.com/dandacompany/oh-my-wiki/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-6C5CE7)](https://github.com/dandacompany/oh-my-wiki#install)
[![skillsmp](https://img.shields.io/badge/skills.sh-oh--my--wiki-1abc9c)](https://skills.sh/)

A host-universal LLM-wiki you drive from your AI coding agent (Claude Code / Codex / Gemini).

oh-my-wiki exposes exactly two surfaces. The **`omw` CLI** handles deterministic ops — `omw setup`, `omw vault create`, `omw lint`, `omw schema list`, `omw supersede`, `omw review`, `omw links`, `omw fields`, `omw view`, `omw doctor` — with no LLM required. The **`omw` skill** brings natural-language reasoning inside your AI session: ingest, query, autoresearch, summary, synthesis, and a set of wiki-maintenance personas (wiki-librarian, wiki-auditor, curator, fact-checker, consistency-checker, terminology-manager). The model is _personas propose → you confirm → deterministic ops execute_, so every file change is auditable. After each op, omw **suggests** the state-endorsed next lifecycle step (`omw next --after <op>`, deterministic; safe default = stop) and lets you confirm or skip — full multi-step orchestration is still left to your host AI agent (Claude Code / Codex / Gemini), not reimplemented here.

**Short alias:** `OMW` (lowercase `omw`). Both `oh-my-wiki` and `omw` register as skills and respond to the same trigger phrases.

**Tutorial:** Walk through real dialogs and verified CLI examples in [TUTORIAL.md](./TUTORIAL.md) (English) or [TUTORIAL.ko.md](./TUTORIAL.ko.md) (한국어).

---

## Current capabilities

- **Schemas** — 13 built-in page types (`omw schema list/show`), with per-vault overrides in `<vault>/schemas/`; generated pages automatically receive missing required sections
- **Confidence + supersede** — `confidence` frontmatter field; `omw supersede` retires old pages cleanly
- **Review queue (SR)** — spaced-repetition via `omw review due` / `omw review done`
- **Web search** — `omw search` queries an external provider (brave/tavily/exa/…); `omw serve` exposes vault FTS5 as a local retrieve-only HTTP API on port 8765
- **Entity-linking** — `omw links suggest` / `omw links link` inserts `[[slug|Name]]` references one at a time or in one confirmed batch with `--from-suggestions`
- **Inline fields** — `omw fields` reads `key::` inline syntax alongside frontmatter
- **Korean matching** — Korean entity names with josa (`카르파시가`) are suggested and linked correctly; NFC/NFD filename differences on macOS and NAS vaults resolve to the same page
- **High-precision recall** — `omw setup recall` combines FTS5, optional local embeddings, Korean normalization, exact-name evidence, bounded body evidence, and conservative relevance filtering before injecting wiki context
- **Cross-session continuity + knowledge candidates** — Claude Code and Codex recall at `SessionStart`, `UserPromptSubmit`, and `PreToolUse`, then stage a small same-project snapshot at `PreCompact` and `Stop`; an opt-in candidate pipeline can turn completed-session decisions and fixes into a review queue without writing the vault, while hook watchdogs fail open and secret patterns are redacted
- **Local embeddings** — `omw embed status/list/use/add/install/reindex` manages FastEmbed plus sqlite-vec, uses a durable cache under `~/.omw/models/fastembed`, and reports per-vault index coverage
- **Note viewers** — `omw view` opens the active vault, a page, or a search in Obsidian or Logseq (URI schemes, no plugin needed); `omw setup viewer` scaffolds the viewer config
- **Visibility (secure-by-default)** — `omw visibility get/set` marks pages `public`/`private`; `omw serve` exposes only public pages
- **URL inbox + fetch** — `omw fetch <url>` saves a web page or YouTube transcript to `raw/` (tiered urllib → chromium → cloud, SSRF-guarded); `omw inbox add/list/run/remove` queues URLs for batch fetch
- **Slash-command family** — each op is also an explicit slash command (`/omw-ingest`, `/omw-query`, `/omw-summary`, `/omw-synthesis`, …) alongside `/omw <op>`; generated at install time from the op registry (see [Slash commands](#slash-commands))
- **Persona slash commands** — one per persona (`/omw-fact-checker`, `/omw-librarian`, `/omw-auditor`, `/omw-curator`, `/omw-consistency-checker`, `/omw-terminology-manager`), each dispatching `omw persona-run <role>`
- **Guided lifecycle chaining** — after a pipeline op, `omw next --after <op>` computes the state-endorsed next op (deterministic — static successor filtered by vault state); the skill offers it via your host's ask tool (safe default = stop, never auto-runs)
- **`summary` / `synthesis` ops** — `omw summary <page>` condenses a page into a summary page; `omw synthesis <topic>` weaves a cluster's structured pages into a `wiki/syntheses/` page
- **Portable vaults** — WSL Korean Windows paths, non-UTF-8 notes, custom `HERMES_HOME`, and NAS/SMB trash fallback are handled without blocking setup or reindex
- **Integrity loop** — all-mode page delete cleans inbound graph edges, inbox fetch reuses matching `source_url`, `omw reindex --full` prunes missing files, and `omw lint` exposes the same structural signal used by session maintenance

---

## Install

Choose whichever path fits your environment. After the PyPI or git path, run `omw doctor` to confirm everything is wired correctly. After the Skills CLI path, the CLI is set up on first use (then `omw doctor`).

### Path A — PyPI (`pip` / `pipx`) — recommended

Install the `omw` CLI from [PyPI](https://pypi.org/project/oh-my-wiki/) without cloning:

```bash
pipx install oh-my-wiki        # isolated CLI (recommended)
# or
pip install oh-my-wiki         # into the current environment
```

Both give you a working `omw` command (`omw status`, `omw vault create …`, `omw lint`, …). The published wheel is self-contained — it bundles the schemas, personas, backends, and the full skill. To register the bundled skill with your agents afterwards, run:

```bash
omw setup agents
```

Installing straight from GitHub works the same way: `pipx install git+https://github.com/dandacompany/oh-my-wiki`.

### Path B — git clone + install script (developers, Codex CLI users)

```bash
git clone https://github.com/dandacompany/oh-my-wiki
cd oh-my-wiki
bash bin/install.sh
```

The installer checks for Python 3.10+, pip-installs the package editable, creates `~/.claude/skills/oh-my-wiki` and `~/.claude/skills/omw` symlinks (idempotent), runs `pytest -q` to verify, and prints next steps. Add `--dev` to include pytest/ruff extras. Use `--force` to replace existing symlinks without a prompt; `--no-test` to skip the test step. Run `bash bin/install.sh --help` for all flags.

### Path C — Skills CLI (Claude Code users)

```bash
skills add dandacompany/oh-my-wiki@oh-my-wiki -g -y --copy -a claude-code
```

This installs the skill into `~/.claude/skills/` and registers both the `oh-my-wiki` and `omw` short-alias skill names. This installs the skill only. The `omw` CLI is installed on first use — open your agent and say **`set up omw`** (or `omw 셋업 점검해줘`); the skill runs its CLI preflight and installs the CLI with your confirmation. Or install it yourself now: `pipx install oh-my-wiki`.

### Verify the install

```
omw doctor
```

```
omw home:   /Users/you/.omw  ok
registry:   /Users/you/.omw/registry.db  ok
  * demo (wiki/markdown) /Users/you/.omw/vaults/demo
```

---

## Quickstart (~60 seconds)

**Step 1 — Run the setup wizard**

```
omw setup
```

Follow the prompts to configure your first vault, search provider, persona preferences,
and recall hooks. Accept the defaults for a fast start. On Codex, open `/hooks` after
setup and approve the new OMW user hooks; installed but untrusted hooks do not run.

**Step 2 — Check status**

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

**Step 3 — Create your first vault**

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

**Step 4 — Add a note (in your AI session)**

Open Claude Code (or Codex / Gemini) and say:

```
ingest this

Andrej Karpathy calls the LLM Wiki a "compounding knowledge artifact". Every
source gets saved verbatim to raw/, a summary lands at wiki/summaries/, and
the entities and concepts that appeared get their own pages. 10–15 page touches
per ingest is normal.
```

**Step 5 — Run a lint check**

```
omw lint
```

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

→ Full tutorial: [TUTORIAL.md](TUTORIAL.md) · [한국어](TUTORIAL.ko.md)

---

## Architecture

```
SKILL.md dispatcher → commands/<op>.md (LLM procedure) → scripts/<op>.py (deterministic I/O)
                                                       └─ registry.py → ~/.omw/registry.db (sqlite)
                                                       └─ recall/session capture → registry.db
                                                       └─ adapters.py → filesystem (markdown / obsidian)
```

Selected top-level commands are shown below. Run `omw help` for the authoritative,
lifecycle-grouped list; it is generated from the same operation registry used by the
agent integrations, so it does not drift when commands are added.

| Subcommand   | Purpose                                                                                              |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `status`     | Show active vault and registry state                                                                 |
| `vault`      | Create, list, use, forget vaults                                                                     |
| `lint`       | Structural health check (frontmatter + links)                                                        |
| `search`     | Web search via the configured external provider (brave/tavily/exa/…)                                 |
| `find`       | Deterministic full-text search over the active vault                                                 |
| `context`    | Retrieve cited hits with page bodies and citations as JSON                                           |
| `embed`      | Manage the local embedding model and its index                                                       |
| `serve`      | Local retrieve-only HTTP query API (port 8765) — public pages only                                   |
| `view`       | Open the vault / a page / a search in Obsidian or Logseq                                             |
| `visibility` | Get / set a page's public/private visibility (`get` / `set`)                                         |
| `schema`     | List / inspect page-type schemas                                                                     |
| `supersede`  | Mark a page superseded by a newer one                                                                |
| `review`     | Spaced-repetition review queue (due / done)                                                          |
| `links`      | Suggest and insert `[[slug]]` entity links                                                           |
| `fields`     | Read frontmatter + inline `key::` fields                                                             |
| `import`     | Import an existing folder as a vault                                                                 |
| `fetch`      | Fetch one URL (web page / YouTube transcript) into `raw/`                                            |
| `inbox`      | Queue URLs and batch-fetch them into `raw/` (add/list/run/remove)                                    |
| `recall`     | Wiki recall and staged-session inspection for agent hooks                                            |
| `next`       | Recommend the next lifecycle action; `--after <op>` gives the state-endorsed next op (deterministic) |
| `setup`      | Interactive setup wizard                                                                             |
| `doctor`     | Verify install health                                                                                |

> **Visibility (secure-by-default):** `omw serve` returns only pages with
> `visibility: public` in their frontmatter. Pages without the field are treated as
> private and never served. Publish pages explicitly with
> `omw visibility set <relpath...> public`.

The skill also exposes natural-language ops via your AI session: `ingest`, `query`, `autoresearch`, `summary`, `synthesis`, `find`, `edit`, `move`, `delete`, and wiki-maintenance persona invocations (`fact-check`, `consistency-check`, `build glossary`). Each is also an explicit slash command — see [Slash commands](#slash-commands).

---

## Slash commands

Every procedure op and every persona is also exposed as an explicit slash command,
generated at install time from the op registry + persona roster (so a new op/persona
auto-gets one, with zero drift). The `/omw <op>` alias still works — these are additive
shortcuts that skip the "which op?" step.

**Op commands** (each dispatches `commands/<op>.md`):

| Command             | Op                                              |
| ------------------- | ----------------------------------------------- |
| `/omw-ingest`       | pull a source into `raw/` and reindex           |
| `/omw-query`        | answer a question from the wiki (LLM synthesis) |
| `/omw-open`         | open a page for reading                         |
| `/omw-edit`         | edit a page following schema conventions        |
| `/omw-move`         | move / rename a page and fix backlinks          |
| `/omw-delete`       | delete a page (confirm first)                   |
| `/omw-autoresearch` | multi-round web research into `raw/`            |
| `/omw-summary`      | condense a page/source into a summary page      |
| `/omw-synthesis`    | weave a cluster's pages into a synthesis page   |

**Persona commands** (each dispatches `omw persona-run <role>`):

| Command                    | Persona                                      |
| -------------------------- | -------------------------------------------- |
| `/omw-librarian`           | tidy structure, cross-links, orphans         |
| `/omw-auditor`             | diagnose what's wrong with the vault         |
| `/omw-curator`             | keep `index.md` in sync and well-ordered     |
| `/omw-fact-checker`        | verify claims via web search, tag confidence |
| `/omw-consistency-checker` | find contradictions within / across pages    |
| `/omw-terminology-manager` | build / maintain the per-vault glossary      |

> **Lifecycle chaining:** after a pipeline op the skill runs `omw next --after <op>`
> and offers the state-endorsed next step (search/fetch → ingest → summary → synthesis
> → lint → review; autoresearch → synthesis). The computation is deterministic; the
> skill asks via your host's tool with a **safe default of stop** and never auto-runs.

---

## Storage

- The vault registry lives at `~/.omw/registry.db` (override with `OMW_HOME`) as a per-user SQLite database. OMW enables WAL so ordinary reads can continue while another process writes.
- `raw/` pages remain searchable evidence but their bracket syntax does not create wiki graph edges or broken-link warnings.
- The note index is regenerated by `scripts/reindex.py` after every mutation.
- Your files stay in the vault path you chose. oh-my-wiki never touches them outside the op you explicitly invoked.
- When staged session capture is enabled (the default), Claude Code and Codex hooks store only the last request, last result, and up to 20 touched file paths in `session_captures` inside the local registry. OMW reads at most the trailing 512 KB of a transcript, caps text at 2,000/4,000 characters, redacts common API-key/token/password/Bearer patterns, keeps at most five captures per project for 30 days, and recalls only the same project. Recalled capture text is framed as escaped, untrusted JSON data so an old message cannot break the session marker. This is local resume context, not a wiki page.
- Inspect staged captures with `omw recall sessions`, hide one from future recall with `omw recall sessions --dismiss <id>`, or disable future capture with `omw setup recall --session-capture off`. Dismissal hides a row; automatic retention removes old rows.
- Session knowledge candidates default to `off`, so upgrades preserve the existing capture behavior. Enable the recommended approval-gated mode with `omw setup recall --knowledge-candidates staged`. `Stop` only captures; classification runs at `PreCompact` or the next session boundary. Hermes captures at `post_llm_call` and processes older session IDs at the next `pre_llm_call`.
- Review with `omw candidates status/list/show`, then explicitly run `omw candidates approve <batch-id>` or `omw candidates dismiss <batch-id>`. Pending batches expire after 30 days. Per-project, host, or vault overrides are available through `omw candidates config`; `auto-raw` is a separate opt-in that writes only high-confidence new items as private, provenance-bearing `raw/` records.
- AgentMemory integration is optional and explicit: export JSON through its documented `GET /agentmemory/export` endpoint, then run `omw candidates run --agentmemory-json <export.json>`. OMW does not read AgentMemory's internal database.

---

## Development

- `pytest -v` runs all tests.
- `ruff check scripts/ tests/` runs the linter.
- `omw status` inspects the registry/vault state.
- `python3 -m scripts.lint --vault-id N` runs the health check on a specific vault.

Continuous integration runs on GitHub Actions, across a matrix of Python 3.10, 3.11, and 3.12 on both ubuntu-latest and macos-latest.

---

## License

Released under the MIT License. See [LICENSE](./LICENSE) for the full text.
