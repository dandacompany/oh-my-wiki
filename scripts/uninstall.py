"""scripts/uninstall.py — safe teardown of omw's host integration.

The inverse of `omw setup`: detect (read-only `plan`) then remove (tier-gated
`apply`) the managed marker blocks, native hooks, and skill bundle omw installed.
Never deletes user knowledge (vaults/registry) without an explicit flag.
stdlib only; `plan()` never raises.
"""
from __future__ import annotations

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
