"""Render a guided CLI overview grouped by lifecycle phase, from the ops_registry
SSOT — so it can never drift from the real op set."""
from __future__ import annotations

from scripts import ops_registry

_PHASE_ORDER = [
    ("capture", "Capture — bring sources in"),
    ("structure", "Structure — organize into the graph"),
    ("synthesize", "Synthesize — combine into new knowledge"),
    ("retrieve", "Retrieve — find what's stored"),
    ("maintain", "Maintain — keep the wiki healthy"),
    ("use", "Use — pull knowledge back out"),
    ("meta", "Setup & introspection"),
]


def render() -> str:
    by_phase: dict[str, list] = {}
    for op in ops_registry.OPS:
        by_phase.setdefault(op.phase or "meta", []).append(op)
    lines = [
        "oh-my-wiki — commands by lifecycle phase",
        "",
        "Usage: omw <command> [options]   ·   omw <command> -h for command details",
        "",
    ]
    for key, header in _PHASE_ORDER:
        ops = sorted(by_phase.get(key, []), key=lambda o: o.name)
        if not ops:
            continue
        lines.append(header)
        for op in ops:
            tag = "[CLI]" if op.kind == "deterministic" else "[skill]"
            lines.append(f"  {op.name:<20} {tag:<7} {op.summary}")
        lines.append("")
    lines.append("Run `omw <command> -h` for command details; deterministic [CLI] ops "
                 "run directly, [skill] ops are executed by the omw agent skill.")
    return "\n".join(lines)
