---
name: oh-my-wiki
description: Karpathy-style LLM Wiki with multi-vault sqlite registry and Socratic wizard. Also addressable by the short alias OMW. Manages multiple knowledge vaults (markdown or Obsidian). On invocation, infers user intent from registry state — first-time users get a setup wizard, returning users go straight to operations. Supports memo-mode (lightweight notes) and wiki-mode (Karpathy's raw/wiki/index/log pattern with ingest/query/lint). Trigger phrases — English "open my wiki", "ingest this", "find a note about X", "what does my wiki say about X", "omw", "use omw", "/omw"; Korean "위키 열어줘", "이거 정리해줘", "X 관련 노트 찾아줘", "위키에 물어봐", "오엠더블유", "오엠더블유 켜줘". Also fires when the user pastes long-form content and asks to save it.
---

# oh-my-wiki (OMW)

A storage-agnostic LLM Wiki skill. Implements Andrej Karpathy's three-layer pattern (Raw / Wiki / Schema) with hybrid `memo-only` and `wiki-mode` per vault. Operations live in `commands/*.md`. Deterministic I/O lives in `scripts/*.py`. State lives in the global registry `~/.omw/registry.db` (override the root with `OMW_HOME`). Vault content lives at each vault's registered path.

**Short alias:** `OMW` (lowercase `omw`). Both `oh-my-wiki` and `omw` resolve to this skill.

## Current status — v1 shipped, v2 in progress

v1 (Plans A + B + C) is complete: dispatcher + foundation scripts, vault management (`vault-setup`, `vault-use`, `vault-list`, `vault-forget`, `vault-import-memo`), memo-mode ops (`create`, `find`, `open`, `edit`, `move`, `delete`), wiki-mode ops (`ingest`, `query`), and the common `lint` op (with wiki-mode structural extensions). 91 pytest tests pass on GitHub Actions matrix (Python 3.10/3.11/3.12 × ubuntu/macos). See `README.md`, `TUTORIAL.md`, `TUTORIAL.ko.md` for usage.

v2 adds plugin-marketplace install, session hot cache, 6 vault-setup modes, extended wiki-lint categories, autoresearch, wiki-maintenance personas (wiki-librarian / curator / fact-checker / consistency-checker / terminology-manager), Obsidian/Logseq viewers, URL fetch + inbox, and per-prompt wiki recall hooks. (Earlier prototypes of a tmux-based multi-agent swarm/team runtime were removed — omw stays focused on the wiki; the host AI agent handles orchestration.)

## Step 1 — Read registry state

Always invoke this before doing anything else:

> **Command interface — read this first.** omw has exactly two ways to run things,
> and NO standalone script CLIs. Do **not** invent filenames like `omw_db.py`,
> `vault.py`, `cli.py`, or `bootstrap.py` — they do not exist.
>
> 1. **Deterministic ops** (status, vault management, lint, search, serve, schema, supersede, review, links, fields, view, visibility, inbox, fetch): run the
>    `omw` CLI — `omw status`, `omw vault list`, `omw vault create <name> --mode wiki`,
>    `omw vault use <name>`, `omw lint`, `omw schema list`, `omw supersede <relpath> --by <slug>`,
>    `omw review due`, `omw serve` (the retrieve-only messenger query API — see `references/messenger-api.md`),
>    `omw view [page] [--search Q] [--viewer obsidian|logseq] [--vault <name>] [--print]` (open vault/page/search in Obsidian or Logseq via URI scheme; companion: `omw setup viewer`),
>    `omw visibility get <relpath>` / `omw visibility set <relpath...> public|private` (per-page visibility management),
>    `omw inbox add <url>` / `omw inbox list` / `omw inbox remove <url>` / `omw inbox run` (queue URLs then batch-fetch into `raw/`),
>    `omw fetch <url> [--backend auto|urllib|chromium|cloud] [--vault] [--today YYYY-MM-DD]` (fetch one URL or YouTube transcript into `raw/`, tiered urllib → chromium → cloud, SSRF-guarded).
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
>    with an automatic token-scorer fallback; `commands/query.md` then LLM-reranks the candidates
>    (no embeddings). Unlinked mentions of existing pages are auto-proposed (`omw links suggest` /
>    `lint`'s `link_suggestions`) and inserted via `omw links link <relpath> --to <slug>`; a page
>    may declare an optional `aliases:` frontmatter list for matching. Pages may also carry inline
>    `key:: value` fields (Dataview line syntax); relation keys (`uses`/`contradicts`/`supersedes:: [[B]]`)
>    feed the typed-edge graph like frontmatter `relations:`, and `omw fields <relpath>` lists a
>    page's frontmatter + inline fields.
> 2. **Reasoning ops** (ingest, query, autoresearch, personas, …): read the exact
>    procedure in `commands/<op>.md` and run its inline `python3 -c` snippet /
>    `python3 -m scripts.<module>` commands verbatim. Never guess a script path.

```bash
python3 -m scripts.wizard status
```

Parse the JSON output. Fields:

- `vault_count` (int)
- `active` (`null` or `{name, path, type, mode}`)
- `needs` (`"setup"` | `"select"` | `"op"`)
- `confirm_target` (bool — `true` when 2+ vaults are registered; see Multi-vault write guard)
- `vaults` (array of `{name, mode}`)

## Step 2 — Route by `needs`

| `needs`     | Action                                                                                                                          |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `"setup"`   | Load `commands/vault-setup.md`.                                                                                                 |
| `"select"`  | Load `commands/vault-use.md`.                                                                                                   |
| `"migrate"` | Load `commands/migrate.md`.                                                                                                     |
| `"op"`      | Inspect the user's input. If it names an op explicitly, load that op's `commands/<op>.md`. Otherwise run the Op Wizard (below). |

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

- **Destructive ops always confirm**: `delete`, `vault-forget`, `--hard` deletes.
- **`vault-forget` never touches files** — only the registry row.
- **Inferred targets are stated**, then confirmed: "방금 작성한 X 메모 말씀이시죠?"
- **No silent fallbacks**: if a vault path is missing on disk, report it and stop. Don't auto-`forget`.
- **Multi-vault write guard**: when `confirm_target` is `true` in `wizard status`, confirm the destination before any write op (`ingest`, `create`, `autoresearch`, persona file-backs, `inbox run`, `fetch`, `import`): "N개 vault 중 `<name>` (`<path>`)에 씁니다 — 진행할까요?". Skip the confirmation if the same vault was already confirmed earlier in this session; reset the confirmation state after any `vault-use` switch.
- **SMB-mounted vaults** (e.g. `/Volumes/...`): use `rsync -rlpt` rather than `cp`. Never `cp -a` on SMB.
- **Recommended option goes first** in any AskUserQuestion list and is suffixed with `(추천)` / `(recommended)`.

## Trigger-phrase routing hint

If the user input matches an op keyword, prefer that op over the wizard:

| Keyword (EN / KO)                                                                  | Op                                                              |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| "ingest", "정리", "흡수"                                                           | `ingest`                                                        |
| "query", "물어봐", "찾아봐"                                                        | `query`                                                         |
| "find", "검색", "찾아줘"                                                           | `find`                                                          |
| "open", "열어줘"                                                                   | `open`                                                          |
| "edit", "수정", "편집"                                                             | `edit`                                                          |
| "move", "이동", "옮겨"                                                             | `move`                                                          |
| "delete", "삭제", "지워"                                                           | `delete`                                                        |
| "lint", "점검", "정리하기"                                                         | `lint`                                                          |
| "setup", "새 vault", "vault 만들기"                                                | `vault-setup`                                                   |
| "use", "vault 전환", "vault 바꿔"                                                  | `vault-use`                                                     |
| "list", "vault 목록"                                                               | `vault-list`                                                    |
| "forget", "vault 제거"                                                             | `vault-forget`                                                  |
| "import memo", "memo 가져오기"                                                     | `vault-import-memo`                                             |
| "autoresearch", "research this", "리서치", "조사"                                  | `autoresearch`                                                  |
| "fact-check this" / "팩트체크해줘"                                                 | `persona-factcheck`                                             |
| "check for contradictions" / "모순 봐줘"                                           | `persona-consistency`                                           |
| "build a glossary" / "용어집 만들어줘"                                             | `persona-terminology`                                           |
| "omw", "OMW", "/omw", "오엠더블유"                                                 | (alias for `oh-my-wiki`; routes through Step 1 wizard normally) |
| "hot-cache", "session cache", "캐시 상태"                                          | `hot-cache`                                                     |
| "view", "open in obsidian", "open in logseq", "뷰어로 열어줘", "옵시디언에서 열어" | `view`                                                          |
| "visibility get", "visibility set", "공개 설정", "비공개 설정", "visibility"       | `visibility`                                                    |
| "inbox add", "inbox list", "inbox run", "큐에 추가", "inbox"                       | `inbox`                                                         |
| "fetch", "fetch this url", "url 가져와", "페이지 가져와"                           | `fetch`                                                         |

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

`vault-setup` accepts these modes: `memo`, `wiki`, `personal`, `book`, `business`, `github-codebase`, `website`. See README "Vault modes (v2.0)" for the layout each one scaffolds.

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
