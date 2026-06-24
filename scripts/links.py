"""Wiki link graph: extract [[wikilink]] + markdown internal [](*.md) refs,
populate the `links` table, resolve to notes by basename-slug, and query
backlinks / orphans / broken-links / graph. Semantic edge types are F#2.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import registry

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:")
_RELATIONS = ("uses", "contradicts", "supersedes",
              "derived-from", "extends", "illustrates", "applies-to",
              "instances-of", "see-also", "synthesizes")

META_RELPATHS = ("wiki/index.md", "wiki/log.md")


def _slugify(target: str) -> str:
    """basename without .md, alias/heading/query stripped, lowercased."""
    t = target.split("|", 1)[0].split("#", 1)[0].split("?", 1)[0]
    t = t.strip().split("/")[-1]
    if t.lower().endswith(".md"):
        t = t[:-3]
    return t.strip().lower()


def extract_links(body: str) -> list[tuple[str, str, int]]:
    """Return [(dst_slug, link_type, position), ...] in document order.

    link_type is 'wikilink' or 'markdown'. External URLs, mailto:, pure
    fragments, and non-.md markdown targets are skipped.
    """
    found: list[tuple[int, str, str]] = []  # (offset, slug, kind)
    for m in _WIKILINK_RE.finditer(body):
        slug = _slugify(m.group(1))
        if slug:
            found.append((m.start(), slug, "wikilink"))
    for m in _MDLINK_RE.finditer(body):
        target = m.group(1).strip()
        low = target.lower()
        if not target or low.startswith(_EXTERNAL_PREFIXES) or target.startswith("#"):
            continue
        path_part = target.split("#", 1)[0].split("?", 1)[0].strip()
        if not path_part.lower().endswith(".md"):
            continue
        slug = _slugify(target)
        if slug:
            found.append((m.start(), slug, "markdown"))
    found.sort(key=lambda x: x[0])
    return [(slug, kind, i) for i, (_, slug, kind) in enumerate(found)]


def extract_relations(meta: dict) -> list[tuple[str, str, int]]:
    """Read frontmatter `relations:` → [(dst_slug, relation, position), ...].

    relations is a dict {uses|contradicts|supersedes: [slug, ...]}. A scalar
    value is treated as a one-item list. Missing/malformed → [].
    """
    rels = (meta or {}).get("relations")
    if not isinstance(rels, dict):
        return []
    out: list[tuple[str, str, int]] = []
    pos = 0
    for relation in _RELATIONS:
        value = rels.get(relation)
        if value is None:
            continue
        targets = value if isinstance(value, list) else [value]
        for target in targets:
            slug = _slugify(str(target))
            if slug:
                out.append((slug, relation, pos))
                pos += 1
    return out


def _value_to_slug(value: str) -> str:
    """Slug from an inline relation value: `[[B]]`/`[[B|d]]` or a bare slug/path."""
    m = _WIKILINK_RE.search(value)
    return _slugify(m.group(1) if m else value)


def extract_inline_relations(body: str) -> list[tuple[str, str, int]]:
    """Read inline `relation:: value` lines → [(dst_slug, relation, position), ...]."""
    from scripts import inline_fields
    fields = inline_fields.extract_inline_fields(body)
    out: list[tuple[str, str, int]] = []
    pos = 0
    for relation in _RELATIONS:
        for value in fields.get(relation, []):
            slug = _value_to_slug(value)
            if slug:
                out.append((slug, relation, pos))
                pos += 1
    return out


def replace_links(db_path: Path, *, vault_id: int, src_note_id: int, body: str,
                  meta: dict | None = None) -> None:
    """Replace all outbound links for one note: body links + frontmatter relations.

    dst_note_id is left NULL (resolve() sets it). The DELETE clears prior body
    links AND relations for this note before re-inserting both.
    """
    edges = list(extract_links(body))
    if meta:
        edges.extend(extract_relations(meta))
    edges.extend(extract_inline_relations(body))
    conn = registry.connect(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM links WHERE src_note_id = ?", (src_note_id,))
            for slug, link_type, position in edges:
                conn.execute(
                    "INSERT INTO links(vault_id, src_note_id, dst_slug, dst_note_id, "
                    "link_type, position) VALUES (?, ?, ?, NULL, ?, ?)",
                    (vault_id, src_note_id, slug, link_type, position),
                )
    finally:
        conn.close()


def resolve(db_path: Path, vault_id: int) -> None:
    """Set links.dst_note_id. A unique alias-owner wins over a unique relpath-owner
    (aliases are authoritative redirects); other collisions resolve to NULL."""
    conn = registry.connect(db_path)
    try:
        with conn:
            relpath_to_ids: dict[str, list[int]] = {}
            alias_to_ids: dict[str, list[int]] = {}
            for row in conn.execute(
                "SELECT id, relpath, aliases FROM notes WHERE vault_id = ?", (vault_id,)
            ):
                relpath_to_ids.setdefault(_slugify(row["relpath"]), []).append(row["id"])
                raw = row["aliases"] if "aliases" in row.keys() else None
                for a in (json.loads(raw) if raw else []):
                    alias_to_ids.setdefault(_slugify(str(a)), []).append(row["id"])
            for row in conn.execute(
                "SELECT DISTINCT dst_slug FROM links WHERE vault_id = ?", (vault_id,)
            ):
                slug = row["dst_slug"]
                aids = alias_to_ids.get(slug, [])
                rids = relpath_to_ids.get(slug, [])
                if len(aids) == 1:
                    dst = aids[0]
                elif len(rids) == 1:
                    dst = rids[0]
                else:
                    dst = None
                conn.execute(
                    "UPDATE links SET dst_note_id = ? WHERE vault_id = ? AND dst_slug = ?",
                    (dst, vault_id, row["dst_slug"]),
                )
    finally:
        conn.close()


def backlinks(db_path: Path, vault_id: int, relpath: str) -> list[dict]:
    """Notes whose links resolve TO the note at `relpath`."""
    conn = registry.connect(db_path)
    try:
        target = conn.execute(
            "SELECT id FROM notes WHERE vault_id = ? AND relpath = ?", (vault_id, relpath)
        ).fetchone()
        if target is None:
            return []
        return [dict(r) for r in conn.execute(
            "SELECT n.relpath, n.title, l.link_type, l.position FROM links l "
            "JOIN notes n ON n.id = l.src_note_id "
            "WHERE l.vault_id = ? AND l.dst_note_id = ? ORDER BY n.relpath, l.position",
            (vault_id, target["id"]),
        )]
    finally:
        conn.close()


def outbound(db_path: Path, vault_id: int, relpath: str) -> list[dict]:
    """Links FROM the note at `relpath` (resolved + broken), in body order."""
    conn = registry.connect(db_path)
    try:
        src = conn.execute(
            "SELECT id FROM notes WHERE vault_id = ? AND relpath = ?", (vault_id, relpath)
        ).fetchone()
        if src is None:
            return []
        return [dict(r) for r in conn.execute(
            "SELECT l.dst_slug, l.link_type, l.position, d.relpath AS dst_relpath, "
            "(l.dst_note_id IS NOT NULL) AS resolved FROM links l "
            "LEFT JOIN notes d ON d.id = l.dst_note_id "
            "WHERE l.src_note_id = ? ORDER BY l.position",
            (src["id"],),
        )]
    finally:
        conn.close()


def orphans(db_path: Path, vault_id: int) -> list[dict]:
    """wiki-layer notes with no inbound resolved link (meta pages excluded)."""
    conn = registry.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in META_RELPATHS)
        return [dict(r) for r in conn.execute(
            "SELECT id, relpath, title FROM notes n "
            "WHERE n.vault_id = ? AND n.layer = 'wiki' "
            f"AND n.relpath NOT IN ({placeholders}) "
            "AND NOT EXISTS (SELECT 1 FROM links l WHERE l.dst_note_id = n.id) "
            "ORDER BY n.relpath",
            (vault_id, *META_RELPATHS),
        )]
    finally:
        conn.close()


def broken_links(db_path: Path, vault_id: int) -> list[dict]:
    """Links whose target slug resolves to no (unique) note."""
    conn = registry.connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT n.relpath AS src_relpath, l.dst_slug, l.link_type, l.position "
            "FROM links l JOIN notes n ON n.id = l.src_note_id "
            "WHERE l.vault_id = ? AND l.dst_note_id IS NULL "
            "ORDER BY n.relpath, l.position",
            (vault_id,),
        )]
    finally:
        conn.close()


def graph(db_path: Path, vault_id: int) -> list[dict]:
    """Full edge list for the vault."""
    conn = registry.connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT s.relpath AS src_relpath, d.relpath AS dst_relpath, l.dst_slug, "
            "l.link_type, (l.dst_note_id IS NOT NULL) AS resolved FROM links l "
            "JOIN notes s ON s.id = l.src_note_id "
            "LEFT JOIN notes d ON d.id = l.dst_note_id "
            "WHERE l.vault_id = ? ORDER BY s.relpath, l.position",
            (vault_id,),
        )]
    finally:
        conn.close()


def relations(db_path: Path, vault_id: int, *, relation: str | None = None) -> list[dict]:
    """Typed semantic edges (uses/contradicts/supersedes). Optionally filter by relation."""
    placeholders = ",".join("?" for _ in _RELATIONS)
    sql = (
        "SELECT s.relpath AS src_relpath, d.relpath AS dst_relpath, l.dst_slug, "
        "l.link_type AS relation, (l.dst_note_id IS NOT NULL) AS resolved FROM links l "
        "JOIN notes s ON s.id = l.src_note_id "
        "LEFT JOIN notes d ON d.id = l.dst_note_id "
        f"WHERE l.vault_id = ? AND l.link_type IN ({placeholders})"
    )
    params: list = [vault_id, *_RELATIONS]
    if relation is not None:
        sql += " AND l.link_type = ?"
        params.append(relation)
    sql += " ORDER BY s.relpath, l.position"
    conn = registry.connect(db_path)
    try:
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def index_drift(db_path: Path, vault_id: int) -> dict:
    """Compare wiki/index.md's outbound links against the wiki page set.

    Returns {"missing_from_index": [{id,relpath,title}, ...],
             "dangling_in_index": [{dst_slug, link_type, position}, ...]}.
    """
    conn = registry.connect(db_path)
    try:
        index_row = conn.execute(
            "SELECT id FROM notes WHERE vault_id = ? AND relpath = 'wiki/index.md'",
            (vault_id,),
        ).fetchone()
        index_id = index_row["id"] if index_row else None
        linked_ids = set()
        dangling = []
        if index_id is not None:
            for r in conn.execute(
                "SELECT dst_note_id, dst_slug, link_type, position FROM links "
                "WHERE src_note_id = ? ORDER BY position",
                (index_id,),
            ):
                if r["dst_note_id"] is None:
                    dangling.append({"dst_slug": r["dst_slug"], "link_type": r["link_type"],
                                     "position": r["position"]})
                else:
                    linked_ids.add(r["dst_note_id"])
        placeholders = ",".join("?" for _ in META_RELPATHS)
        missing = [dict(r) for r in conn.execute(
            "SELECT id, relpath, title FROM notes "
            "WHERE vault_id = ? AND layer = 'wiki' "
            f"AND relpath NOT IN ({placeholders}) "
            "ORDER BY relpath",
            (vault_id, *META_RELPATHS),
        ) if r["id"] not in linked_ids]
        return {"missing_from_index": missing, "dangling_in_index": dangling}
    finally:
        conn.close()
