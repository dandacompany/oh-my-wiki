"""Host-universal persona export.

Advertise the enabled persona roster in each host's instruction file
(CLAUDE.md / AGENTS.md / GEMINI.md) via a symmetric marker block. Deliberately
NOT claude-native `.claude/agents/` — omw is a universal skill (claude/codex/
gemini), so no host's native subagent mechanism is privileged. The host-agnostic
invocation path is the omw skill itself (`commands/persona-*.md`).
"""
from __future__ import annotations

from pathlib import Path

HOST_FILES = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "gemini": "GEMINI.md"}
MARKER = "omw-personas"
_START = f"<!-- {MARKER}:start -->"
_END = f"<!-- {MARKER}:end -->"


def _dispatch_policy_lines(enabled: list[str], routes: dict[str, list[str]] | None) -> list[str]:
    """The always-on routing table + persona-vs-host dispatch policy. This is what
    makes a matching persona auto-fire (or get offered to the user) when a request
    arrives — host-universal, since the omw-personas block is read every session."""
    out: list[str] = ["", "### Dispatch — route a request to the right persona", ""]
    routes = routes or {}
    rows = [(n, routes.get(n) or []) for n in enabled if routes.get(n)]
    if rows:
        out += ["When a request matches one of these domains, that persona is the candidate:", ""]
        for name, trigs in rows:
            out.append(f"- **{name}** ← " + ", ".join(f'"{t}"' for t in trigs))
        out.append("")
    out += [
        "On a matching request, decide: **delegate** to the persona subagent "
        "(`omw persona-run <role>`) or let the **host** handle it inline (the host wins "
        "when context transfer to an isolated one-shot subagent is impractical).",
        "",
        "**Ask the user which**, using the host's question tool — Claude Code: "
        "AskUserQuestion; Hermes: the clarify tool; other hosts: a plain inline question. "
        "Offer: (1) delegate to the persona subagent, with an **\"auto for this session\"** "
        "variant; (2) host handles it. If the host has no question tool, pick a sensible "
        "default (delegate when the persona clearly fits, else host) and say so in one line.",
        "",
        "**Session-sticky (avoid fatigue):** once the user picks the **auto** variant, do "
        "NOT ask again for the rest of this session — auto-dispatch matching personas "
        "automatically. Likewise if they pick \"host handles it,\" keep that as the session "
        "default. omw has no host session id, so remember this choice in your own "
        "conversation context for the duration of the session.",
    ]
    return out


def render_block(enabled: list[str], main: str, descriptions: dict[str, str],
                 routes: dict[str, list[str]] | None = None) -> str:
    """Render the omw-personas marker block (pure; no I/O).

    `routes` maps persona name -> trigger phrases; when given, a routing table is
    rendered. The dispatch policy is always emitted (it needs no routes)."""
    lines = [
        _START,
        "## omw personas (managed by `omw setup personas` — do not edit between markers)",
        "",
        f"Main persona: **{main}**",
        "",
        "Enabled personas:",
    ]
    for name in enabled:
        desc = (descriptions.get(name) or "").strip().replace("\n", " ")
        lines.append(f"- **{name}** — {desc}" if desc else f"- **{name}**")
    lines += [
        "",
        'Invoke any of these via the omw skill — e.g. say "research X", '
        '"audit the wiki", or run a team. Persona definitions live in '
        "`personas/<name>.md`; procedures in `commands/persona-*.md`.",
    ]
    lines += _dispatch_policy_lines(enabled, routes)
    lines.append(_END)
    return "\n".join(lines)


def upsert_marker(md_path: Path, block: str) -> None:
    """Insert or replace the omw-personas marker region in md_path (idempotent).

    Creates the file if absent; preserves everything outside the markers.
    """
    md_path = Path(md_path)
    text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    if _START in text and _END in text:
        pre = text[: text.index(_START)]
        post = text[text.index(_END) + len(_END):]
        new = pre + block + post
    elif text == "":
        new = block + "\n"
    else:
        sep = "\n" if text.endswith("\n") else "\n\n"
        new = text + sep + block + "\n"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(new, encoding="utf-8")


def export_personas(*, enabled: list[str], main: str, descriptions: dict[str, str],
                    base_dir: Path, hosts: list[str], profile: str | None = None,
                    workspace: str | None = None,
                    routes: dict[str, list[str]] | None = None) -> list[Path]:
    """Write the roster block into each selected host's instruction file (deduped
    by resolved path — codex/opencode share AGENTS.md)."""
    from scripts import hosts as hostsmod
    base_dir = Path(base_dir)
    block = render_block(enabled, main, descriptions, routes=routes)
    written: list[Path] = []
    seen: set = set()
    for host in hosts:
        path = hostsmod.resolve_instruction_path(host, base_dir,
                                                 profile=profile, workspace=workspace)
        if path in seen:
            continue
        seen.add(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        upsert_marker(path, block)
        written.append(path)
    return written
