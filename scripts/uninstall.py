"""scripts/uninstall.py — safe teardown of omw's host integration.

The inverse of `omw setup`: detect (read-only `plan`) then remove (tier-gated
`apply`) the managed marker blocks, native hooks, and skill bundle omw installed.
Never deletes user knowledge (vaults/registry) without an explicit flag.
stdlib only; `plan()` never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import persona_export, recall, commandmap

#: The four managed marker names, sourced from their owning modules (SSOT).
MARKERS: tuple[str, ...] = (
    persona_export.MARKER,        # "omw-personas"
    recall.MARKER,                # "omw-recall"
    recall.ALWAYS_ON_MARKER,      # "omw-wiki-first"
    commandmap.MARKER,            # "omw-commandmap"
)


def strip_marker_block(text: str, marker: str) -> tuple[str, bool]:
    """Remove the inclusive `<!-- {marker}:start -->`…`<!-- {marker}:end -->` region.

    Preserves everything outside the fences; collapses the seam to at most one
    blank line; ensures a single trailing newline when the result is non-empty.
    Returns (new_text, removed). No-op (text, False) if a fence is missing.
    """
    start = f"<!-- {marker}:start -->"
    end = f"<!-- {marker}:end -->"
    i = text.find(start)
    j = text.find(end)
    if i == -1 or j == -1 or j < i:
        return text, False
    pre = text[:i].rstrip("\n")
    post = text[j + len(end):].lstrip("\n")
    if pre and post:
        new = pre + "\n\n" + post
    else:
        new = pre + post
    if new and not new.endswith("\n"):
        new += "\n"
    return new, True


def _is_omw_recall_cmd(cmd: str) -> bool:
    """Mirror recall._event_has_recall: an omw recall hook invocation."""
    return "recall" in cmd and ("preamble" in cmd or "prompt" in cmd or "pretool" in cmd)


def _strip_omw_hooks(config_path) -> tuple[int, bool]:
    """Remove only omw-recall hook groups from one host hook JSON. Returns
    (removed_count, changed). Best-effort; never raises."""
    path = Path(config_path)
    if not path.exists():
        return 0, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, False
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        return 0, False
    hooks = data["hooks"]
    removed = 0
    for event in list(hooks.keys()):
        groups = hooks.get(event) or []
        kept = []
        for group in groups:
            inner = (group or {}).get("hooks", []) if isinstance(group, dict) else []
            if any(_is_omw_recall_cmd((h if isinstance(h, dict) else {}).get("command", "")) for h in inner):
                removed += 1
            else:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del data["hooks"]
    if removed:
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        except OSError:
            return 0, False
    return removed, removed > 0
