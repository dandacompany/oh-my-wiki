"""Single source of truth for omw's user-facing ops.

Every op fact (kind, args, hints, CLI template / procedure file) lives here once.
The CLI builds its agentic subparsers from PROCEDURE_NAMES, `cards.py` renders
procedure cards from an OpSpec, `commandmap.py` renders the host command-map
block, and the anti-drift test pins SKILL.md / hooks / gate prose to this list.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class ArgSpec:
    name: str            # "topic" (positional) or "--rounds" (flag)
    required: bool
    hint: str
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class OpSpec:
    name: str
    kind: str            # "deterministic" | "procedure"
    summary: str
    args: tuple[ArgSpec, ...] = ()
    cli_template: str | None = None      # deterministic ops
    procedure_file: str | None = None    # procedure ops -> "commands/<op>.md"
    uses: tuple[str, ...] = ()            # downstream ops a procedure calls
    phase: str | None = None             # lifecycle phase (capture/structure/synthesize/retrieve/maintain/use/meta)


def _det(name, summary, cli_template, args=()):
    return OpSpec(name=name, kind="deterministic", summary=summary,
                  cli_template=cli_template, args=tuple(args))


def _proc(name, summary, args=(), uses=()):
    return OpSpec(name=name, kind="procedure", summary=summary,
                  procedure_file=f"commands/{name}.md", args=tuple(args), uses=tuple(uses))


OPS: tuple[OpSpec, ...] = (
    # --- deterministic CLI ops (run them; trust the result) ---
    _det("status", "Show registry state as JSON.", "omw status"),
    _det("vault", "Deterministic vault management.", "omw vault {list|create|use|forget} …"),
    _det("lint", "Run deterministic lint over a vault.", "omw lint [--vault V]"),
    _det("reindex", "Rebuild the search/graph index.", "omw reindex [--full] [--vault V]"),
    _det("connections", "Community/bridge/hub graph as JSON.", "omw connections [--no-reindex]"),
    _det("fields", "Show a page's frontmatter + inline fields.", "omw fields <page>"),
    _det("links", "Entity-link suggestions + insertion.", "omw links {suggest|link} …"),
    _det("review", "Spaced-repetition review queue.", "omw review {due|done|audit|use} …"),
    _det("supersede", "Mark a page superseded.", "omw supersede <page> <by>"),
    _det("merge", "Consolidate a source page into a target (alias + tombstone); staged proposal.",
         "omw merge <source> <target> [--force] [--apply <proposal>]",
         args=(ArgSpec("source", False, "page merged away (becomes a tombstone)"),
               ArgSpec("target", False, "winner page that survives"),
               ArgSpec("--force", False, "allow merging pages of different types"),
               ArgSpec("--apply", False, "apply a staged <winner>.proposed.md"))),
    _det("visibility", "Get/set a page's serve visibility.", "omw visibility {get|set} …"),
    _det("inbox", "URL inbox queue (add/list/remove/run/retry).", "omw inbox {add|add-feed|list|remove|run|retry} …"),
    _det("fetch", "Fetch one URL into raw/ (no LLM).", "omw fetch <url> [--backend auto|urllib|chromium|cloud]",
         args=(ArgSpec("url", True, "page URL to fetch"),
               ArgSpec("--backend", False, "fetch backend", ("auto", "urllib", "chromium", "cloud")))),
    _det("schema", "Show page-type schemas.", "omw schema {list|show} …"),
    _det("search", "Web search via the configured provider. Auto-falls back across keyed providers.", "omw search <query> [--provider P] [--limit N]",
         args=(ArgSpec("query", True, "web search query"),
               ArgSpec("--provider", False, "override search provider"),
               ArgSpec("--limit", False, "max results (default 10)"),
               ArgSpec("--no-fallback", False, "single configured provider only (default: auto-fallback across keyed providers)"))),
    _det("serve", "Run the local query HTTP API (retrieve-only).", "omw serve …"),
    _det("view", "Open vault/page/search in a note viewer.", "omw view [page] [--viewer obsidian|logseq]"),
    _det("recall", "Wiki recall for agent hooks.", "omw recall {preamble|pretool|prompt} …"),
    _det("maint", "Knowledge-maintenance status (cron-friendly).", "omw maint status"),
    _det("gate", "Maintenance gate: note moments / turn-end check.", "omw gate {note|check} …"),
    _det("setup", "Interactive setup wizard.", "omw setup [section] …"),
    _det("import", "Import folder/Obsidian/Notion into a vault.", "omw import --source folder|obsidian|notion …"),
    _det("doctor", "Validate omw config + install.", "omw doctor"),
    _det("update", "Self-upgrade omw (env-aware) + refresh managed host blocks.",
         "omw update [--check] [--yes] [--no-refresh]",
         args=(ArgSpec("--check", False, "report current→latest only; do not upgrade"),
               ArgSpec("--yes", False, "skip confirmation (non-interactive)"),
               ArgSpec("--no-refresh", False, "do not regenerate managed blocks after upgrade"))),
    _det("next", "Recommend the next knowledge-lifecycle action(s) from vault state.",
         "omw next [--vault V] [--json]",
         args=(ArgSpec("--vault", False, "vault name (default: active)"),
               ArgSpec("--json", False, "emit the ranked suggestions as JSON"))),
    _det("list", "Faceted note listing (by tag/type/status/layer/visibility) as JSON.",
         "omw list [--tag T] [--type T] [--status S] [--layer L] [--visibility V]",
         args=(ArgSpec("--tag", False, "filter by tag"),
               ArgSpec("--type", False, "filter by page type"),
               ArgSpec("--status", False, "filter by status"),
               ArgSpec("--layer", False, "filter by layer (raw/wiki/memo/meta)"),
               ArgSpec("--visibility", False, "filter by visibility (public/private)"))),
    _det("context", "Deterministic cited-context retrieval (hits + bodies + citations) for grounded answers.",
         "omw context <query> [--limit N]",
         args=(ArgSpec("query", True, "the question / search text"),
               ArgSpec("--limit", False, "max hits (default 8)"))),
    _det("find", "Deterministic full-text search over the vault index.",
         "omw find <query> [--limit N] [--vault V] [--json]",
         args=(ArgSpec("query", True, "search text (title/slug/tags/snippet)"),
               ArgSpec("--limit", False, "max hits (default 10)"),
               ArgSpec("--vault", False, "vault name (default: active)"),
               ArgSpec("--json", False, "emit JSON instead of a text table"))),
    _det("export", "Export a vault slice (by tag/type/visibility) to a self-contained Markdown dir or zip.",
         "omw export [--tag T] [--type T] [--visibility V] [--out DIR | --zip FILE]",
         args=(ArgSpec("--tag", False, "select pages by tag"),
               ArgSpec("--type", False, "select pages by type"),
               ArgSpec("--visibility", False, "select pages by visibility"),
               ArgSpec("--out", False, "output directory"),
               ArgSpec("--zip", False, "output zip file"),
               ArgSpec("--force", False, "allow exporting into a non-empty directory"))),
    _det("help", "Guided CLI overview grouped by lifecycle phase.", "omw help"),
    _det("persona-run", "Dispatch a persona as an isolated one-shot subagent (any backend).",
         "omw persona-run <role> [--page P|--file F|--text T] [--backend B] [--apply PROP]",
         args=(ArgSpec("role", True, "persona name (fact-checker, consistency-checker, curator, terminology-manager, wiki-librarian)"),
               ArgSpec("--backend", False, "claude|codex|gemini|opencode (default: first authed)",
                       ("claude", "codex", "gemini", "opencode")))),
    # --- agentic procedures (you execute commands/<op>.md; do NOT trust a shelled result) ---
    _proc("ingest", "Pull a source (path/URL) into raw/ and reindex.",
          args=(ArgSpec("source", True, "file path or URL"),), uses=("fetch", "reindex")),
    _proc("query", "Answer a question from the wiki (LLM synthesis).",
          args=(ArgSpec("question", True, "natural-language question"),
                ArgSpec("--vault", False, "vault name (default: active)"))),
    _proc("open", "Open a page for reading in the session.",
          args=(ArgSpec("page", True, "page relpath or slug"),)),
    _proc("edit", "Edit a page following schema conventions.",
          args=(ArgSpec("page", True, "page relpath or slug"),)),
    _proc("move", "Move/rename a page and fix backlinks.",
          args=(ArgSpec("src", True, "source page"), ArgSpec("dst", True, "destination relpath"))),
    _proc("delete", "Delete a page (confirm first).",
          args=(ArgSpec("page", True, "page relpath or slug"),)),
    _proc("autoresearch", "Multi-round web research into raw/ (no synthesis unless asked).",
          args=(ArgSpec("topic", True, "research subject, free text"),
                ArgSpec("--rounds", False, "search rounds (default 3)"),
                ArgSpec("--no-synthesis", False, "collect raw only; build no synthesis page")),
          uses=("search", "fetch", "reindex")),
    # Personas: dispatched as an isolated subagent via `omw persona-run <role>`, NOT inline role-play.
    _proc("persona-factcheck", "Fact-checker persona — dispatched via `omw persona-run <role>` (isolated subagent).",
          args=(ArgSpec("page", True, "page/text/file to fact-check"),)),
    _proc("persona-consistency", "Consistency-checker persona — dispatched via `omw persona-run <role>` (isolated subagent).",
          args=(ArgSpec("page", False, "page to check (default: whole vault)"),)),
    _proc("persona-terminology", "Terminology-manager persona — dispatched via `omw persona-run <role>` (isolated subagent).",
          args=(ArgSpec("page", False, "page to scan (default: whole vault)"),)),
)

_PHASE = {
    # capture — bring sources in
    "inbox": "capture", "fetch": "capture", "import": "capture", "ingest": "capture",
    # structure — organize into the graph
    "reindex": "structure", "links": "structure", "fields": "structure",
    "connections": "structure", "open": "structure", "edit": "structure",
    "move": "structure", "delete": "structure",
    # synthesize — combine into new knowledge
    "query": "synthesize", "context": "synthesize", "autoresearch": "synthesize",
    # retrieve — find what's stored
    "search": "retrieve", "find": "retrieve", "serve": "retrieve",
    # maintain — keep the wiki healthy
    "lint": "maintain", "review": "maintain", "supersede": "maintain", "merge": "maintain",
    "visibility": "maintain", "gate": "maintain", "maint": "maintain", "next": "maintain",
    "recall": "maintain", "persona-run": "maintain", "persona-factcheck": "maintain",
    "persona-consistency": "maintain", "persona-terminology": "maintain",
    # use — pull knowledge back out
    "view": "use", "list": "use", "export": "use",
    # meta — setup / introspection
    "status": "meta", "vault": "meta", "setup": "meta", "doctor": "meta",
    "update": "meta", "schema": "meta", "help": "meta",
}

OPS = tuple(dataclasses.replace(op, phase=_PHASE.get(op.name, "meta")) for op in OPS)

_BY_NAME = {op.name: op for op in OPS}


def get(name: str) -> OpSpec | None:
    return _BY_NAME.get(name)


def names() -> tuple[str, ...]:
    return tuple(op.name for op in OPS)


def procedures() -> tuple[str, ...]:
    return tuple(op.name for op in OPS if op.kind == "procedure")


def deterministic() -> tuple[str, ...]:
    return tuple(op.name for op in OPS if op.kind == "deterministic")


PROCEDURE_NAMES: tuple[str, ...] = tuple(op.name for op in OPS if op.kind == "procedure")
