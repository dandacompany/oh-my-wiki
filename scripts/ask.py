"""omw-ask: host-universal 'ask the user for judgment' convention.

omw upgrades the *confirm* in its `propose → confirm → execute` invariant into a
**structured** choice, rendered with whatever native ask-surface the host has. This
module is the SSOT for (a) the per-host ask surface (`ASK`), (b) the wiki-lifecycle
decision-class taxonomy (`TAXONOMY`), and (c) the rendered `omw-ask` managed block.

Survey-grounded (2026-06): four hosts have a near-isomorphic structured-question tool
(Claude AskUserQuestion / Gemini ask_user / opencode question / Hermes clarify); Codex
uses requestUserInput + MCP elicitation; openclaw has no question tool — its only
in-process decision primitive is requireApproval (binary) + async channel buttons. The
universal failure mode is non-interactive/headless → the degrade rule applies.

Mirrors commandmap.py: MARKER + render_block() + export(base_dir, hosts).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MARKER = "omw-ask"
_START = f"<!-- {MARKER}:start -->"
_END = f"<!-- {MARKER}:end -->"


# ── per-host ask surface (SSOT) ──────────────────────────────────────────────
# tool   = the native surface the host renders the abstract ask with
# shape  = how the abstract ask DTO maps onto it
# headless = what the host does with no interactive surface (drives the degrade rule)
ASK: dict[str, dict] = {
    "claude": {"tool": "AskUserQuestion", "kind": "structured",
               "shape": "questions[].{question, header≤12, options[2-4].{label,description}, multiSelect}; add an 'Other' option manually",
               "headless": "errors → degrade"},
    "codex": {"tool": "requestUserInput", "kind": "structured-appserver",
              "shape": "{label, description, isOther} (isOther = freeform); or MCP elicitation/create",
              "headless": "exec auto-cancels → degrade"},
    "gemini": {"tool": "ask_user", "kind": "structured",
               "shape": "questions[].{question, header≤16, type: choice|text|yesno, options[2-4].{label,description}, multiSelect}",
               "headless": "throws → degrade"},
    "hermes": {"tool": "clarify", "kind": "structured",
               "shape": "{question, choices[≤4]} (auto-appends an 'Other (type)' choice)",
               "headless": "600s timeout → None → degrade"},
    "opencode": {"tool": "question", "kind": "structured",
                 "shape": "{question, header, options[2-4].{label,description}, multiSelect} (+ Other)",
                 "headless": "hangs → pre-resolve / degrade"},
    "openclaw": {"tool": "requireApproval", "kind": "binary",
                 "shape": "binary approve/deny gate (before_tool_call); N-way only via async channel buttons",
                 "headless": "timeout → deny (= safe default)"},
}


# ── decision-class taxonomy ──────────────────────────────────────────────────
@dataclass(frozen=True)
class Decision:
    key: str
    phase: str
    when: str                 # the trigger moment
    options: tuple[str, ...]  # safe default FIRST
    safe_default: str
    destructive: bool = False
    sticky: bool = True       # may the user pick 'do this for the session'?


def _d(key, phase, when, options, *, destructive=False):
    # safe default is always the first option; destructive classes are never sticky
    return Decision(key=key, phase=phase, when=when, options=tuple(options),
                    safe_default=options[0], destructive=destructive,
                    sticky=not destructive)


TAXONOMY: tuple[Decision, ...] = (
    # capture
    _d("duplicate-ingest", "capture", "incoming source ≈ existing raw/page",
       ("Skip", "Ingest anyway", "Merge into existing")),
    _d("vault-target", "capture", "multi-vault and target is ambiguous",
       ("Active vault", "Choose another vault")),
    # structure
    _d("new-vs-update", "structure", "a distilled page ≈ an existing page",
       ("Propose as new", "Update existing", "Show diff first")),
    _d("page-type", "structure", "page type is ambiguous",
       ("note", "entity", "synthesis", "comparison")),
    _d("insert-links", "structure", "N cross-link suggestions are available",
       ("None", "Selected links")),  # multi-select in practice
    _d("move-backlinks", "structure", "move/rename would rewrite M backlinks",
       ("Rewrite backlinks", "Move only", "Cancel")),
    # synthesize
    _d("autoresearch-synthesize", "synthesize", "autoresearch finished",
       ("Leave in raw", "Synthesize into a page now")),
    # maintain
    _d("stale-page", "maintain", "wiki-auditor flags a stale/expired page",
       ("Leave", "Refresh", "Supersede", "Archive")),
    _d("merge-candidates", "maintain", "near-duplicate pages found",
       ("Keep separate", "Merge into target"), destructive=True),
    _d("contradiction-canonical", "maintain", "a contradiction is found",
       ("Flag only", "Side A is canonical", "Side B is canonical")),
    _d("supersede", "maintain", "page A is superseded by B",
       ("No", "Yes, mark superseded"), destructive=True),
    _d("delete-page", "maintain", "a delete is requested",
       ("Cancel", "Soft-delete to trash", "Hard delete"), destructive=True),
    _d("visibility-publish", "maintain", "publishing a page to the serve API",
       ("Keep private", "Make public")),
    _d("persona-delegate", "maintain", "a request matches a persona's domain",
       ("Host handles it", "Delegate to persona (+auto for session)")),
    # use
    _d("export-scope", "use", "exporting a vault slice",
       ("Markdown dir", "Zip", "Single file")),
)


def destructive_keys() -> set[str]:
    return {d.key for d in TAXONOMY if d.destructive}


# ── rendered managed block ───────────────────────────────────────────────────
_HOST_ORDER = ("claude", "codex", "gemini", "hermes", "opencode", "openclaw")


def render_block() -> str:
    lines = [
        _START,
        "## omw ask-for-judgment (managed by `omw setup recall` — do not edit between markers)",
        "",
        "When a wiki save/structure step reaches a genuine fork that needs the user's "
        "judgment, **ask with a structured choice** — this is the *confirm* in omw's "
        "`propose → confirm → execute`, upgraded from plain text. Ask only at real forks "
        "(user-owned trade-offs or irreversible/outward effects); never for trivial, "
        "reversible, or obvious-default steps. List the **safe (non-destructive) option "
        "first**. Do the asking in the **host orchestrator, never inside a spawned "
        "persona subagent** (rule: question → host, execution → subagent).",
        "",
        "### Use your host's native ask surface",
        "",
        "| host | tool | how to shape the ask |",
        "| --- | --- | --- |",
    ]
    for h in _HOST_ORDER:
        d = ASK[h]
        lines.append(f"| {h} | `{d['tool']}` | {d['shape']} |")
    lines += [
        "",
        "**Degrade rule (non-interactive / headless / no tool):** do NOT block — take the "
        "decision's **safe default**, print a one-line `<omw-ask>` note saying what was "
        "chosen and why, and proceed. (openclaw is async/gateway: prefer a binary approval "
        "gate; its timeout already defaults to the safe option.)",
        "",
        "**Session-sticky (anti-fatigue):** once the user picks a '…for this session' "
        "variant of a decision class, stop re-asking that class this session and apply "
        "their choice (kept in your conversation context). **Destructive ops "
        "(merge/supersede/delete/overwrite) ALWAYS ask and ALWAYS default to the "
        "non-destructive branch — never auto-applied, even under session 'auto'.**",
        "",
        "### Decision classes — when to ask + safe default",
        "",
        "| class | phase | when | safe default | options |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in TAXONOMY:
        flag = " ⚠destructive" if d.destructive else ""
        opts = " · ".join(d.options)
        lines.append(f"| `{d.key}`{flag} | {d.phase} | {d.when} | **{d.safe_default}** | {opts} |")
    lines.append(_END)
    return "\n".join(lines)


def export(base_dir, hosts: list[str], *, profile: str | None = None,
           workspace: str | None = None) -> None:
    """Upsert the omw-ask block into each host's instruction file (deduped by
    resolved path — codex/opencode share AGENTS.md). Mirrors commandmap.export."""
    from scripts import hosts as hostsmod
    from scripts import recall
    base_dir = Path(base_dir)
    block = render_block()
    seen: set = set()
    for host in hosts:
        path = hostsmod.resolve_instruction_path(host, base_dir,
                                                 profile=profile, workspace=workspace)
        if path in seen:
            continue
        seen.add(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        recall.upsert_block(path, block, MARKER)
