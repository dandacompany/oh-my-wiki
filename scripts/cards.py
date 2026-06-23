"""Render a procedure card from an OpSpec + the args the user bound on the CLI.

A card tells the agent: this op is a procedure (needs an omw skill session), here
are your bound arguments, here are the deterministic ops it will use, and here is
the steps file to follow. It replaces the old "unrecognized arguments" / generic
stub so that shelling an agentic op never dead-ends.
"""
from __future__ import annotations

import json

from scripts.ops_registry import OpSpec


def _bound_lines(spec: OpSpec, bound: dict) -> list[str]:
    lines = []
    for a in spec.args:
        key = a.name.lstrip("-").replace("-", "_")
        if key in bound and bound[key] not in (None, False):
            lines.append(f"  {a.name.lstrip('-')}: {bound[key]}")
    return lines


def render_card(spec: OpSpec, bound: dict) -> str:
    out = [f"→ procedure: {spec.name}  (needs omw skill)"]
    out += _bound_lines(spec, bound)
    if spec.uses:
        out.append(f"  uses: {' → '.join(spec.uses)}")
    out.append(f"  steps: {spec.procedure_file}")
    out.append("  hint: run this procedure in your session; "
               "do NOT expect a deterministic result.")
    return "\n".join(out)


def render_card_json(spec: OpSpec, bound: dict) -> str:
    args = {}
    for a in spec.args:
        key = a.name.lstrip("-").replace("-", "_")
        if key in bound and bound[key] not in (None, False):
            args[key] = bound[key]
    return json.dumps({
        "procedure": spec.name,
        "args": args,
        "uses": list(spec.uses),
        "steps": spec.procedure_file,
    }, ensure_ascii=False)
