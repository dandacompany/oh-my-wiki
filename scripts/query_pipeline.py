"""Deterministic cited-context retrieval for `omw context`.

Runs the configured retrieval strategy, reads each hit's body, and returns a
structured bundle (hits + bodies + a citations manifest) so the host agent can
synthesize an answer grounded ONLY in real retrieved pages — no citation
hallucination. Read-only; never mutates the vault."""
from __future__ import annotations

from pathlib import Path

from scripts import config, embed, frontmatter, links, recall, registry, search_index


def context(db_path: Path, *, vault_id: int, q: str, limit: int = 8,
            body_cap: int = 4000) -> dict:
    rc = config.load_config().get("recall") or {}
    strat = recall.effective_strategy(rc.get("strategy", "fts"), quiet=True)
    embedder = embed.active_embedder(
        db_path, rc.get("embedding") or {}
    ) if strat != "fts" else None
    hits = search_index.search_strategy(
        db_path, vault_id=vault_id, q=q, limit=limit, strategy=strat,
        embedder=embedder, visibility=None)
    root = registry.get_vault_root(db_path, vault_id)
    out_hits: list[dict] = []
    citations: list[dict] = []
    for h in hits:
        relpath = h["relpath"]
        slug = links._slugify(relpath)
        title = h.get("title") or slug
        body = ""
        abs_path = root / relpath
        body_missing = not abs_path.exists()
        if not body_missing:
            _meta, body = frontmatter.parse(abs_path.read_text(encoding="utf-8"))
        truncated = len(body) > body_cap
        if truncated:
            body = body[:body_cap]
        out_hits.append({
            "slug": slug, "relpath": relpath, "title": title,
            "score": h.get("score", 0), "body": body, "truncated": truncated,
            "body_missing": body_missing,
        })
        citations.append({"slug": slug, "title": title, "relpath": relpath})
    return {"query": q, "strategy": strat, "hits": out_hits, "citations": citations}
