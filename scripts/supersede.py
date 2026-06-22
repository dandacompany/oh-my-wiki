"""Deterministic supersession marking: set status: superseded + superseded_by.

This is the 'execute' half of the propose→confirm→execute lifecycle; a persona
(wiki-auditor) proposes, the human runs `omw supersede`, this writes the page.
"""
from __future__ import annotations

from pathlib import Path

from scripts import frontmatter, registry, reindex


def mark_superseded(db_path: Path, *, vault_id: int, relpath: str, by_slug: str) -> dict:
    """Set status: superseded + superseded_by on a page, then reindex. Idempotent."""
    root = registry.get_vault_root(db_path, vault_id)  # raises VaultError if vault is unknown
    abs_path = root / relpath
    if not abs_path.exists():
        raise FileNotFoundError(f"page not found: {relpath}")
    meta, body = frontmatter.parse(abs_path.read_text(encoding="utf-8"))
    meta["status"] = "superseded"
    meta["superseded_by"] = by_slug
    abs_path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    reindex.incremental(db_path, vault_id=vault_id)
    return {"relpath": relpath, "status": "superseded", "superseded_by": by_slug}
