"""Single source of truth for omw's user-facing ops.

Every op fact (kind, args, hints, CLI template / procedure file) lives here once.
The CLI builds its agentic subparsers from PROCEDURE_NAMES, `cards.py` renders
procedure cards from an OpSpec, `commandmap.py` renders the host command-map
block, and the anti-drift test pins SKILL.md / hooks / gate prose to this list.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
    _det("visibility", "Get/set a page's serve visibility.", "omw visibility {get|set} …"),
    _det("inbox", "URL inbox queue.", "omw inbox {add|list|remove|run} …"),
    _det("fetch", "Fetch one URL into raw/ (no LLM).", "omw fetch <url> [--backend auto|urllib|chromium|cloud]",
         args=(ArgSpec("url", True, "page URL to fetch"),
               ArgSpec("--backend", False, "fetch backend", ("auto", "urllib", "chromium", "cloud")))),
    _det("schema", "Show page-type schemas.", "omw schema {list|show} …"),
    _det("search", "Web search via the configured provider.", "omw search <query> [--provider P] [--limit N]",
         args=(ArgSpec("query", True, "web search query"),
               ArgSpec("--provider", False, "override search provider"),
               ArgSpec("--limit", False, "max results (default 10)"))),
    _det("serve", "Run the local query HTTP API (retrieve-only).", "omw serve …"),
    _det("view", "Open vault/page/search in a note viewer.", "omw view [page] [--viewer obsidian|logseq]"),
    _det("recall", "Wiki recall for agent hooks.", "omw recall {preamble|pretool|prompt} …"),
    _det("maint", "Knowledge-maintenance status (cron-friendly).", "omw maint status"),
    _det("gate", "Maintenance gate: note moments / turn-end check.", "omw gate {note|check} …"),
    _det("setup", "Interactive setup wizard.", "omw setup [section] …"),
    _det("import", "Import folder/Obsidian/Notion into a vault.", "omw import --source folder|obsidian|notion …"),
    _det("doctor", "Validate omw config + install.", "omw doctor"),
    _det("find", "Deterministic full-text search over the vault index.",
         "omw find <query> [--limit N] [--vault V] [--json]",
         args=(ArgSpec("query", True, "search text (title/slug/tags/snippet)"),
               ArgSpec("--limit", False, "max hits (default 10)"),
               ArgSpec("--vault", False, "vault name (default: active)"),
               ArgSpec("--json", False, "emit JSON instead of a text table"))),
    # --- agentic procedures (you execute commands/<op>.md; do NOT trust a shelled result) ---
    _proc("ingest", "Pull a source (path/URL) into raw/ and reindex.",
          args=(ArgSpec("source", True, "file path or URL (repeatable)"),), uses=("fetch", "reindex")),
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
    # Personas: dispatched as an isolated subagent (Workstream D), NOT inline role-play.
    _proc("persona-factcheck", "Dispatch the fact-checker persona subagent (Workstream D).",
          args=(ArgSpec("page", True, "page/text/file to fact-check"),)),
    _proc("persona-consistency", "Dispatch the consistency-checker persona subagent (Workstream D).",
          args=(ArgSpec("page", False, "page to check (default: whole vault)"),)),
    _proc("persona-terminology", "Dispatch the terminology-manager persona subagent (Workstream D).",
          args=(ArgSpec("page", False, "page to scan (default: whole vault)"),)),
)

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
