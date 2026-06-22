"""Wiki-mode query helpers. Most of query is an LLM workflow; this is the file-back side."""
from __future__ import annotations

from pathlib import Path

from scripts import frontmatter, ingest, registry, slugify


def write_synthesis(
    db_path: Path,
    *,
    vault_id: int,
    title: str,
    body: str,
    citations: list[str],
    tags: list[str],
    date_str: str,
    summary: str | None = None,
) -> str:
    """Write a synthesis page under wiki/syntheses/. Returns relpath.

    `summary` (if given) lands in frontmatter — it lifts search/recall ranking
    (the FTS scorer weights summary heavily) and feeds the index/hot cache.
    """
    root = registry.get_vault_root(db_path, vault_id)

    base = slugify.slugify(title)
    relpath = ingest._resolve_path(root, "wiki/syntheses", base, "md")
    meta = {
        "title": title,
        "date": date_str,
        "type": "synthesis",
        "tags": list(tags),
        "status": "processed",
        "citations": list(citations),
    }
    if summary:
        meta["summary"] = summary
    abs_path = root / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return relpath
