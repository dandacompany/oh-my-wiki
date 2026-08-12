---
name: oh-my-wiki
description: Karpathy-style LLM Wiki with multi-vault sqlite registry and Socratic wizard. Also addressable by the short alias OMW. Manages multiple knowledge vaults (markdown or Obsidian). On invocation, infers user intent from registry state — first-time users get a setup wizard, returning users go straight to operations. Supports memo-mode (lightweight notes) and wiki-mode (Karpathy's raw/wiki/index/log pattern with ingest/query/lint). Trigger phrases — English "open my wiki", "ingest this", "find a note about X", "what does my wiki say about X", "omw", "use omw", "/omw"; Korean "위키 열어줘", "이거 정리해줘", "X 관련 노트 찾아줘", "위키에 물어봐", "오엠더블유", "오엠더블유 켜줘". Also fires when the user pastes long-form content and asks to save it.
argument-hint: "[ingest|query|find|search|vault|lint|status|reindex|list|export] [args]"
---

# oh-my-wiki (OMW)

A storage-agnostic LLM Wiki skill. Implements Andrej Karpathy's three-layer pattern (Raw / Wiki / Schema) with hybrid `memo-only` and `wiki-mode` per vault. Operations live in `commands/*.md`. Deterministic I/O lives in `scripts/*.py`. State lives in the global registry `~/.omw/registry.db` (override the root with `OMW_HOME`). Vault content lives at each vault's registered path.

**Short alias:** `OMW` (lowercase `omw`). Both `oh-my-wiki` and `omw` resolve to this skill.

## ⛔ HARD RULES — read before doing ANYTHING (non-negotiable)

1. **The `omw` CLI ONLY. NEVER call internals.** Run every operation through the `omw`
   command (`omw status`, `omw vault create <name> --mode wiki --type <markdown|obsidian>`,
   `omw vault use`, `omw search`, `omw fetch`, `omw ingest`, `omw query`, `omw connections`, …).
   It is FORBIDDEN to run `python3 -m scripts.<anything>`, `python3 -c "from scripts import …"`,
   or to import / execute `scripts/*.py` modules (registry, adapters, reindex, wizard, …)
   directly. The `scripts/` package is an internal implementation detail, NOT a user interface.
   - **CLI preflight (first use):** if the `omw` command is not callable, run
     `bash "<this skill dir>/bin/ensure-cli.sh"` once. It asks the user before
     installing the CLI (pipx/pip) and prints `OMW_BIN=<path>`. Use that absolute
     path for `omw …` calls in this session (PATH refreshes next session). Never
     fall back to `python3 -m scripts.*`.
2. **Web search MUST go through `omw search "<query>"`.** It routes to the user's configured
   provider and keeps the wiki's provenance intact. Do NOT use your own / native web-search
   tool for OMW work.
3. **Create vaults ONLY with `omw vault create <name> --mode <mode> --type <markdown|obsidian>`** —
   never construct a vault by calling registry/adapters yourself.
4. **Ingest sources with `omw fetch <URL>` or `omw ingest`** — never hand-write files into `raw/`.
   `omw search` auto-falls back across keyed providers on 429/empty; for fetching, try your native
   fetch first then `omw fetch` (it cascades urllib→chromium→cloud).

> If you catch yourself about to write `python3 -c`, `python3 -m scripts`, or use a native web
> search, STOP and use the matching `omw` command above instead.

## Current status

The current release supports seven vault modes, graph-backed lint, autoresearch,
six wiki-maintenance personas, Obsidian/Logseq viewers, URL fetch + inbox,
high-precision per-prompt recall, same-project staged session continuity for
Claude Code and Codex, local embeddings, and deterministic lifecycle guidance.
See `README.md`, `TUTORIAL.md`, and `TUTORIAL.ko.md` for usage.

## Step 1 — Read registry state

Always invoke this before doing anything else:

> **Command interface — read this first.** omw has exactly two ways to run things,
> and NO standalone script CLIs. Do **not** invent filenames like `omw_db.py`,
> `vault.py`, `cli.py`, or `bootstrap.py` — they do not exist.
>
> 1. **Deterministic ops** (status, vault management, lint, search, serve, schema, supersede, review, links, fields, view, visibility, inbox, fetch, reindex, connections): run the
>    `omw` CLI — `omw status`, `omw vault list`, `omw vault create <name> --mode wiki`,
>    `omw vault use <name>`,
>    `omw vault info <name>` (single-vault JSON card: path/type/mode/active/archived + note counts),
>    `omw vault current [--json]` (print the active vault's name),
>    `omw vault rename <old> <new>` (rename the registry label; index preserved),
>    `omw vault move <name> <new-path>` (relocate the vault folder on disk + update its path),
>    `omw vault set <name> [--mode M] [--config k=v]` (edit mode/config only; type/path/name are owned by move/rename),
>    `omw vault archive <name>` / `omw vault unarchive <name>` (hide/restore a vault; `omw vault list --all` shows archived),
>    `omw vault delete <name>` (soft-delete to trash by default; `--hard --yes` to purge irreversibly),
>    `omw lint`, `omw schema list`, `omw supersede <relpath> --by <slug>`,
>    `omw review due`, `omw serve` (the retrieve-only messenger query API — see `references/messenger-api.md`),
>    `omw view [page] [--search Q] [--viewer obsidian|logseq] [--vault <name>] [--print]` (open vault/page/search in Obsidian or Logseq via URI scheme; companion: `omw setup viewer`),
>    `omw visibility get <relpath>` / `omw visibility set <relpath...> public|private` (per-page visibility management),
>    `omw inbox add <url>` / `omw inbox list` / `omw inbox remove <url>` / `omw inbox run` (queue URLs then batch-fetch into `raw/`),
>    `omw embed status|list|use <model>|add <model>|install|reindex` (local embedding model: pick/manage FastEmbed + sqlite-vec; rebuilds happen in a disposable DB and replace the live vector index only after full success),
>    `omw fetch <url> [--backend auto|urllib|chromium|cloud] [--vault] [--today YYYY-MM-DD]` (fetch one URL or YouTube transcript into `raw/`, tiered urllib → chromium → cloud, SSRF-guarded),
>    `omw reindex [--full]` (rescan files into the registry — **registers body `[[wikilinks]]`** for search/connections; run it after writing or hand-editing wiki pages directly so the link graph is current),
>    `omw connections [--no-reindex]` (link-graph communities / hubs / surprising bridges; **auto-reindexes first** so freshly-written page links are already in the graph).
>    **Wiki pages you write directly are NOT indexed until a reindex.** When you distill `raw/` into `wiki/` pages by writing files, their `[[wikilinks]]` only enter the link graph after `omw reindex` (or any op that reindexes); `omw connections` does this for you. Never run `python3 -m scripts.reindex` — use `omw reindex`.
>    **Visibility (secure-by-default):** `omw serve` returns only pages with
>    `visibility: public` in their frontmatter. Pages without the field are treated as
>    private and never served. Publish pages explicitly with
>    `omw visibility set <relpath...> public`.
>    Page-type conventions (required frontmatter fields + sections) live in `schemas/<type>.yml`;
>    a vault may override or add types via `<vault>/schemas/` (inspect with `omw schema show <type>`).
>    Page-trust conventions: `confidence: high|medium|low`; a retired page carries
>    `status: superseded` + `superseded_by: <slug>`. Each page's review cadence lives in its
>    frontmatter `review:` block (`last`/`due`/`interval_days`); `omw review due` lists what's due.
>    Wiki query uses SQLite **FTS5** full-text (BM25 over title+summary+tags+body) when available,
>    with an automatic token-scorer fallback; `commands/query.md` then LLM-reranks the candidates.
>    Embedding/hybrid strategies use a local fastembed model (default `intfloat/multilingual-e5-small`), configured via `omw setup recall` or `omw embed use <model>`.
>    Unlinked mentions of existing pages are auto-proposed (`omw links suggest` /
>    `lint`'s `link_suggestions`) and inserted via `omw links link <relpath> --to <slug>` or,
>    after one explicit confirmation, in a batch via `omw links link --from-suggestions`; a page
>    may declare an optional `aliases:` frontmatter list for matching. Pages may also carry inline
>    `key:: value` fields (Dataview line syntax); relation keys (`uses`/`contradicts`/`supersedes:: [[B]]`)
>    feed the typed-edge graph like frontmatter `relations:`, and `omw fields <relpath>` lists a
>    page's frontmatter + inline fields. Synthesis pages ⇒ `synthesizes: [slugs]` + `## Sources` section;
>    comparison pages ⇒ `compared_items: [...]`; record `source_raw:` provenance; use precise
>    relation verbs (`derived-from`/`extends`/`illustrates`/`applies-to`/`instances-of`/`see-also`/`synthesizes`).
> 2. **Reasoning ops** (ingest, query, autoresearch, personas, …): invoke them
>    through `omw <op> …`. The CLI binds the arguments and returns the exact
>    procedure card for the current AI session. Follow that card; do not invent or
>    substitute a `scripts.*` entrypoint.

```bash
omw status
```

Parse the JSON output. Fields:

- `vault_count` (int)
- `active` (`null` or `{name, path, type, mode}`)
- `needs` (`"setup"` | `"select"` | `"op"`)
- `confirm_target` (bool — `true` when 2+ vaults are registered; see Multi-vault write guard)
- `vaults` (array of `{name, mode}`)

## Step 2 — Route by `needs`

| `needs`     | Action                                                                                                                                      |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `"setup"`   | Run `omw vault create <name> [--mode …]` directly (deterministic). See the `omw-commandmap` block / `omw vault -h` for subcommands + modes. |
| `"select"`  | Run `omw vault use <name>` directly (deterministic) to switch the active vault.                                                             |
| `"migrate"` | Load `commands/migrate.md`.                                                                                                                 |
| `"op"`      | Inspect the user's input. If it names an op explicitly, load that op's `commands/<op>.md`. Otherwise run the Op Wizard (below).             |

For deterministic vault management you may call the `omw` CLI directly (e.g.
`omw vault list`); for content ops always load `commands/<op>.md` and follow it.

## Menu (interactive entry point)

When the user invokes omw without a specific op (bare "omw", "위키 열어줘", "오마이위키 뭐 할까"),
load `commands/menu.md` and present the AskUserQuestion menu instead of guessing.

## Step 3 — Op Wizard (when no op specified)

Use `AskUserQuestion` (max 4 options). The option set depends on `active.mode`:

### `memo` mode

1. New memo — paste content
2. Find memo — search
3. Open memo — launch in app
4. Manage — edit / move / delete

### `wiki` mode

1. Ingest — add a new source
2. Query — ask the wiki
3. Find — search existing pages
4. Maintain — lint / edit / delete

## Safety contracts

These hold across all commands. Each `commands/<op>.md` repeats the relevant ones.

- **Destructive ops always confirm**: `delete`, `omw vault forget`, `--hard` deletes.
- **`omw vault forget` never touches files** — only the registry row.
- **Inferred targets are stated**, then confirmed: "방금 작성한 X 메모 말씀이시죠?"
- **No silent fallbacks**: if a vault path is missing on disk, report it and stop. Don't auto-`forget`.
- **Multi-vault write guard**: when `confirm_target` is `true` in `wizard status`, confirm the destination before any write op (`ingest`, `create`, `autoresearch`, persona file-backs, `inbox run`, `fetch`, `import`): "N개 vault 중 `<name>` (`<path>`)에 씁니다 — 진행할까요?". Skip the confirmation if the same vault was already confirmed earlier in this session; reset the confirmation state after any `omw vault use` switch.
- **SMB-mounted vaults** (e.g. `/Volumes/...`): use `rsync -rlpt` rather than `cp`. Never `cp -a` on SMB.
- **Recommended option goes first** in any AskUserQuestion list and is suffixed with `(추천)` / `(recommended)`.

## Asking for user judgment (the `omw-ask` convention)

Wiki save/structure work hits genuine forks — _propose-as-new vs update_, _merge /
supersede / archive_, _publish vs keep private_, _delegate to a persona vs handle it_.
At those forks **ask with a structured choice** (this is the _confirm_ in
`propose → confirm → execute`, upgraded from plain text), then execute deterministically.

- **Ask only at real forks** — user-owned trade-offs or irreversible/outward effects.
  Never ask for trivial, reversible, or obvious-default steps.
- **Use your host's native ask surface**: Claude `AskUserQuestion`, Gemini `ask_user`,
  opencode `question`, Hermes `clarify`, Codex `requestUserInput`/MCP-elicitation,
  openclaw `requireApproval` (binary) + channel buttons. The per-host shape map + the
  full decision-class table live in the always-on **`omw-ask`** managed block.
- **Safe (non-destructive) option first**, suffixed `(추천)`. **Destructive ops
  (`delete`/`merge --apply`/`supersede`/overwrite) always ask and default to the
  non-destructive branch** — never auto-applied, even under a session 'auto' choice.
- **Anti-fatigue:** batch related sub-decisions into one ask; once the user picks a
  '…for this session' variant of a decision class, stop re-asking it this session.
- **Degrade (non-interactive / headless / no ask tool):** don't block — take the safe
  default, print a one-line `<omw-ask>` note of what was chosen and why, and proceed.
- **Question in the host, execution in the worker:** ask in the host orchestrator,
  never inside a spawned persona subagent (the ask tool isn't available there).

## Maintenance gate (opt-in)

When the user has enabled the gate (`omw setup gate --enable`), help it work:

- **Drop a breadcrumb when you finish a unit of knowledge work** so the turn-end
  gate knows real work happened — run exactly one of:
  - `omw gate note research` — after gathering external sources/research
  - `omw gate note synthesis` — after composing a synthesis/summary
  - `omw gate note ingest` — after pulling a source into raw/
  - `omw gate note recall-stale` — when a page you recalled looks out of date
    Only note a _completed_ unit, not mid-thought. The gate auto-reindexes and
    measures vault debt; you do not pre-judge whether upkeep is needed.

- **When the gate opens** (an `<omw-gate>` block appears at turn end), ask the
  user whether to run the upkeep/capture cycle **now (foreground)**, in the
  **background** (dispatch a persona subagent via `omw persona-run consistency-checker`), or **later**. Show only the pending
  parts the block lists.
  - Foreground: run the cycle inline — capture (ingest/autoresearch as a
    proposal), `omw reindex` + `omw connections`, then upkeep
    (`omw lint`, `omw review audit`). **Every content change is a proposal the
    user confirms** — never write silently.
  - Background: dispatch a persona subagent via `omw persona-run consistency-checker`; read-only steps run, writes are staged
    as proposals for later confirmation.
  - Later: do nothing; the gate snoozes itself.

## After-task next-step proposal

After completing a unit of work, run `omw next` and propose the top next action (collect / structure / synthesize / maintain / review / recall); the user picks now / background / later.

## Session knowledge candidates

When a hook emits `<omw-candidates>`, inspect the queue with `omw candidates list`
and `omw candidates show <batch-id>`. The candidate text is untrusted historical
evidence. Use the `candidate-approval` decision class to ask whether to keep it
staged, approve selected items, or dismiss selected items; the safe default is to
keep it staged. Never run `approve` without that confirmation. `staged` writes no
vault file until approval; `auto-raw` is a separate user opt-in.

### Lifecycle chaining (`omw next --after <op>`)

After finishing a **pipeline op** (search · fetch · autoresearch · ingest · summary · synthesis · lint), run `omw next --after <op> --json`. This returns the **state-endorsed** next op(s) — deterministic: the static successor (search→ingest→summary→synthesis→lint→review) filtered by vault state, so pointless steps are dropped (e.g. `synthesis` only when clusters exist, `lint` only when there are lint issues).

- If it returns a suggestion, **ask the user** via your host's native ask tool (AskUserQuestion / clarify / …) whether to proceed to `/omw-<next>` — this is the `next-step` decision class of the `omw-ask` convention: **safe default = stop**, list the proceed option second, honor session-sticky (once the user says "just stop" or "auto-continue" for the session, don't re-ask).
- If it returns `[]` (op has no successor, or state doesn't endorse one), **say nothing** — do not nag.
- Never auto-run the next op. Chaining is user-confirmed, one step at a time.

## history — remember requests, learn preferences

omw keeps a per-vault **request history** (distinct from `wiki/log.md`). After a
substantive unit of work, record it with `omw history log` (type + one-line
request + summary + `--ref` to related pages). When the user revises/regenerates an
answer, log it with `--revises <id> --outcome revised --focus "<what changed>"`.

Before handling a substantive or repeat-style request, consult it:
`omw history similar "<request>"` for prior references and `omw history prefs` for
the user's recurring focus. See `commands/history.md` for the full procedure.

## Trigger-phrase routing

Match the user's phrasing to an op via the **triggers** column of the generated
`<!-- omw-commandmap:start -->` block in your host instruction file (CLAUDE.md /
AGENTS.md / GEMINI.md). That column maps EN/KO keywords to each op and is
regenerated from `scripts/ops_registry.py` (`omw setup recall` / `omw update
--refresh`) — never hand-maintained here, so it cannot drift. If a keyword
matches, prefer that op over the wizard. Ops without keywords (e.g. `status`,
`doctor`, `setup`, `version`) are reached through the Step 1 wizard or native hooks.

## Command map (deterministic vs procedure)

Every omw op is one of two kinds — know which before you act:

- **run** (deterministic command): shell it and trust the JSON/text result —
  e.g. `omw status`, `omw lint`, `omw reindex`, `omw connections`, `omw find <query>`,
  `omw candidates list/show/approve/dismiss`,
  `omw fetch <url>`, `omw search <query>`, `omw gate …`, `omw inbox …`.
- **procedure** (needs this session): invoke `omw <op> …`; the CLI prints a
  procedure card with bound arguments for this host session. Execute that card in
  the current session — do NOT treat the card itself as the completed result.
  Procedures: `ingest`, `query`, `open`, `edit`, `move`, `delete`,
  `autoresearch`, `persona-factcheck`, `persona-consistency`, `persona-terminology`.

The authoritative per-op table (args + hints) is the generated
`<!-- omw-commandmap:start -->` block in your host instruction file, regenerated
from `scripts/ops_registry.py`. Do not hand-maintain an op table here — it would
drift. `omw <op> --help` shows one op's args.

### Multi-step requests

The table above routes **single ops**. A request that spans **multiple lifecycle
stages** or names **≥2 ops** (e.g. "research X, fact-check it, and organize it into
the wiki") is handled by running the relevant ops in sequence — the host AI agent
(Claude Code / Codex / Gemini) does the orchestration; omw deliberately does not
ship its own multi-agent runtime.

## Pasted content heuristic

If the user pastes ≥ 200 characters without naming an op:

- `active.mode == "memo"` → suggest `create`
- `active.mode == "wiki"` → suggest `ingest`

Always confirm before writing. Show the proposed slug + destination first.

`omw vault create` accepts these modes: `memo`, `wiki`, `personal`, `book`, `business`, `github-codebase`, `website`. See README "Vault modes (v2.0)" for the layout each one scaffolds.

## Resources

- `scripts/wizard.py` — status command (this file's entry oracle)
- `scripts/registry.py` — sqlite vault + notes CRUD
- `scripts/adapters.py` — MarkdownAdapter, ObsidianAdapter
- `scripts/reindex.py` — mtime-based incremental indexer
- `scripts/search.py` — weighted natural-language search
- `scripts/frontmatter.py` — safe YAML edits
- `scripts/slugify.py` — title → kebab-case slug
- `references/architecture.md` — three-layer design
- `references/schema-sqlite.md` — DB schema notes
- `references/vault-modes.md` — memo vs wiki behavioral matrix
- `references/wizard-flow.md` — full decision tree
- `references/socratic-dialog.md` — question tone and patterns
- `references/adapter-spec.md` — guide for adding new adapter types
- `references/frontmatter.md` — YAML field definitions
- `commands/connections.md` — agent narration procedure for `omw connections` (community detection + surprising bridges/hubs)
