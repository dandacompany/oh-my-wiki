"""Deterministic page-usage side store: `<vault>/.oh-my-wiki/usage.json`.

Records the last date each page was actually *surfaced* (recall/query/serve), so
freshness can reactivate on real use — separate from the review schedule and
WITHOUT mutating page frontmatter on every read (mirrors Hermes' `.usage.json`).
Best-effort: never raises to callers (recall runs on every prompt).
"""
from __future__ import annotations

import json
from pathlib import Path


def _path(vault_root) -> Path:
    return Path(vault_root) / ".oh-my-wiki" / "usage.json"


def load(vault_root) -> dict:
    p = _path(vault_root)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def last_used(vault_root) -> dict:
    """relpath -> last-used ISO date (YYYY-MM-DD)."""
    data = load(vault_root)
    used = data.get("last_used")
    return used if isinstance(used, dict) else {}


def bump(vault_root, relpaths, today: str) -> bool:
    """Record `today` as last_used for each relpath. Returns True if written.
    Best-effort — swallows I/O errors (e.g. read-only sandbox)."""
    rels = [r for r in (relpaths or []) if r]
    if not rels:
        return False
    try:
        data = load(vault_root)
        used = data.get("last_used")
        if not isinstance(used, dict):
            used = {}
            data["last_used"] = used
        for r in rels:
            used[r] = today
        p = _path(vault_root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False
