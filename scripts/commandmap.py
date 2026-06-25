"""Generate the `omw-commandmap` managed block from ops_registry and upsert it
into host instruction files (CLAUDE.md / AGENTS.md / GEMINI.md), mirroring
persona_export.py. One row per op so the agent always knows run-vs-procedure.
"""
from __future__ import annotations

from pathlib import Path

from scripts import ops_registry as reg
from scripts import recall
from scripts.persona_export import HOST_FILES  # noqa: F401  # re-exported for back-compat

MARKER = "omw-commandmap"
_START = f"<!-- {MARKER}:start -->"
_END = f"<!-- {MARKER}:end -->"


def _row(op) -> str:
    if op.kind == "deterministic":
        return f"| `{op.name}` | run | `{op.cli_template}` | {op.summary} |"
    parts = [a.name if a.name.startswith("--") else f"<{a.name}>" for a in op.args]
    invocation = " ".join(["omw", op.name, *parts]).rstrip()
    return f"| `{op.name}` | procedure | `{invocation}` → {op.procedure_file} | {op.summary} |"


def render_block() -> str:
    lines = [
        _START,
        "## omw command map (managed by `omw setup recall` — do not edit between markers)",
        "",
        "Each op is either **run** (a deterministic command — shell it, trust the result)",
        "or a **procedure** (execute the steps file in your session; do not trust a shelled result).",
        "",
        "| op | kind | invocation | what it does |",
        "| --- | --- | --- | --- |",
    ]
    lines += [_row(op) for op in reg.OPS]
    lines.append(_END)
    return "\n".join(lines)


def export(base_dir: Path, hosts: list[str], *, profile: str | None = None,
           workspace: str | None = None) -> None:
    from scripts import hosts as hostsmod
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
