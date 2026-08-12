"""Ingest-time entity linking: propose [[wikilinks]] for unlinked page mentions.

Deterministic detection (suggest_links) + a deterministic insertion op
(apply_link). Personas/commands propose which suggestions to accept; the human
runs `omw links link` — no auto-write at ingest.
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts import frontmatter, links, registry, reindex, text_match

_EXEMPT = set(links.META_RELPATHS)


def _name_pattern(names) -> re.Pattern | None:
    return text_match.build_name_pattern(names)


def _link_spans(body: str) -> list[tuple[int, int]]:
    spans = [(m.start(), m.end()) for m in links._WIKILINK_RE.finditer(body)]
    spans += [(m.start(), m.end()) for m in links._MDLINK_RE.finditer(body)]
    return spans


def _in_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _entities(db_path: Path, *, vault_id: int) -> list[dict]:
    root = registry.get_vault_root(db_path, vault_id)
    ents: list[dict] = []
    for md in sorted(root.rglob("*.md")):
        if ".trash" in md.parts or md.name.endswith(".proposed.md"):
            continue
        rel = str(md.relative_to(root)).replace("\\", "/")
        if rel in _EXEMPT or rel.startswith("raw/"):
            continue
        try:
            meta, _ = frontmatter.parse(md.read_text(encoding="utf-8"))
        except frontmatter.FrontmatterError:
            continue
        aliases = meta.get("aliases") if isinstance(meta.get("aliases"), list) else []
        names = [n for n in ([meta.get("title")] + [str(a) for a in aliases]) if n]
        if names:
            ents.append({"slug": links._slugify(rel), "relpath": rel, "names": names})
    return ents


def suggest_links(db_path: Path, *, vault_id: int, relpath=None) -> list[dict]:
    root = registry.get_vault_root(db_path, vault_id)
    ents = _entities(db_path, vault_id=vault_id)
    for e in ents:
        e["pat"] = _name_pattern(e["names"])
    out: list[dict] = []
    for md in sorted(root.rglob("*.md")):
        if ".trash" in md.parts or md.name.endswith(".proposed.md"):
            continue
        rel = str(md.relative_to(root)).replace("\\", "/")
        if rel in _EXEMPT or rel.startswith("raw/"):
            continue
        if relpath is not None and rel != relpath:
            continue
        try:
            _, body = frontmatter.parse(md.read_text(encoding="utf-8"))
        except frontmatter.FrontmatterError:
            continue
        spans = _link_spans(body)
        already = {slug for slug, _, _ in links.extract_links(body)}
        for e in ents:
            if e["relpath"] == rel or e["slug"] in already or not e["pat"]:
                continue
            for m in e["pat"].finditer(body):
                if not _in_span(m.start(), spans):
                    out.append({"src_relpath": rel, "target_slug": e["slug"],
                                "target_relpath": e["relpath"], "mention": m.group("name"),
                                "position": m.start()})
                    break
    return out


def apply_link(db_path: Path, *, vault_id: int, relpath: str, target_slug: str,
               reindex_after: bool = True) -> dict:
    root = registry.get_vault_root(db_path, vault_id)
    abs_path = root / relpath
    if not abs_path.exists():
        raise FileNotFoundError(f"page not found: {relpath}")
    target = next((e for e in _entities(db_path, vault_id=vault_id)
                   if e["slug"] == target_slug), None)
    if target is None:
        raise ValueError(f"no page with slug {target_slug!r}")
    meta, body = frontmatter.parse(abs_path.read_text(encoding="utf-8"))
    pat = _name_pattern(target["names"])
    spans = _link_spans(body)
    match = next((m for m in (pat.finditer(body) if pat else [])
                  if not _in_span(m.start(), spans)), None)
    if match is None:
        raise ValueError(f"no unlinked mention of {target_slug!r} in {relpath}")
    mention = match.group("name")
    repl = f"[[{target_slug}]]" if links._slugify(mention) == target_slug \
        else f"[[{target_slug}|{mention}]]"
    new_body = body[:match.start("name")] + repl + body[match.end("name"):]
    abs_path.write_text(frontmatter.dump(meta, new_body), encoding="utf-8")
    if reindex_after:
        reindex.incremental(db_path, vault_id=vault_id)
    return {"relpath": relpath, "target_slug": target_slug, "mention": mention, "inserted": repl}


def apply_suggestions(db_path: Path, *, vault_id: int, limit: int | None = None,
                      dry_run: bool = False) -> dict:
    """Apply the current deterministic suggestion set in one process.

    Pages are re-read before each insertion, then the vault is reindexed once at
    the end. A repeated invocation sees no remaining suggestions and is a no-op.
    """
    suggestions = suggest_links(db_path, vault_id=vault_id)
    if limit is not None:
        suggestions = suggestions[:max(0, limit)]
    if dry_run:
        return {
            "dry_run": True,
            "planned": suggestions,
            "applied": [],
            "skipped": [],
            "failed": [],
            "counts": {"planned": len(suggestions), "applied": 0,
                       "skipped": 0, "failed": 0},
        }
    applied = []
    skipped = []
    failed = []
    seen = set()
    for suggestion in suggestions:
        pair = (suggestion["src_relpath"], suggestion["target_slug"])
        if pair in seen:
            skipped.append({**suggestion, "reason": "duplicate suggestion"})
            continue
        seen.add(pair)
        try:
            applied.append(apply_link(
                db_path, vault_id=vault_id, relpath=pair[0], target_slug=pair[1],
                reindex_after=False,
            ))
        except ValueError as exc:
            skipped.append({**suggestion, "reason": str(exc)})
        except Exception as exc:
            failed.append({**suggestion, "error": str(exc)})
    if applied:
        reindex.incremental(db_path, vault_id=vault_id)
    return {
        "dry_run": False,
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "counts": {"applied": len(applied), "skipped": len(skipped), "failed": len(failed)},
    }
