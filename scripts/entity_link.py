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
        if ".trash" in md.parts:
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
        if ".trash" in md.parts:
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


def apply_link(db_path: Path, *, vault_id: int, relpath: str, target_slug: str) -> dict:
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
    reindex.incremental(db_path, vault_id=vault_id)
    return {"relpath": relpath, "target_slug": target_slug, "mention": mention, "inserted": repl}
