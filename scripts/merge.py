"""Deterministic page merge: consolidate a source page into a target (winner).

Stages `<target>.proposed.md` (union frontmatter + merged body + alias) and
`<source>.proposed.md` (tombstone). Real pages are written only by `apply()`.
Never touches unrelated pages or the vault registry; link survival is via the
winner's `aliases:` (see links.resolve), not by rewriting referencing bodies.
"""
from __future__ import annotations

from pathlib import Path

from scripts import frontmatter, links, reindex, registry


class MergeError(Exception):
    """Raised on an invalid merge (type mismatch, already-merged, slug conflict)."""


def _proposal_path(abs_path: Path) -> Path:
    return abs_path.with_name(abs_path.name + ".proposed.md")


def _union(*lists) -> list:
    out: list = []
    for lst in lists:
        for item in (lst or []):
            if item not in out:
                out.append(item)
    return out


def stage(db_path: Path, *, vault_id: int, source_relpath: str,
          target_relpath: str, force: bool = False) -> dict:
    root = registry.get_vault_root(db_path, vault_id)
    src_abs = root / source_relpath
    tgt_abs = root / target_relpath
    if not src_abs.exists():
        raise FileNotFoundError(f"source page not found: {source_relpath}")
    if not tgt_abs.exists():
        raise FileNotFoundError(f"target page not found: {target_relpath}")
    if src_abs.resolve() == tgt_abs.resolve():
        raise MergeError("source and target are the same page")

    src_meta, src_body = frontmatter.parse(src_abs.read_text(encoding="utf-8"))
    tgt_meta, tgt_body = frontmatter.parse(tgt_abs.read_text(encoding="utf-8"))

    if src_meta.get("status") == "merged":
        raise MergeError(
            f"{source_relpath} is already merged into {src_meta.get('merged_into')!r}")
    if not force and src_meta.get("type") != tgt_meta.get("type"):
        raise MergeError(
            f"type mismatch: source is {src_meta.get('type')!r}, target is "
            f"{tgt_meta.get('type')!r}; pass force=True to merge across types")

    src_slug = links._slugify(source_relpath)
    tgt_slug = links._slugify(target_relpath)

    # Refuse if source-slug is also a THIRD live page's relpath-slug (authoring conflict).
    conn = registry.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT relpath FROM notes WHERE vault_id = ?", (vault_id,)
        ).fetchall()
    finally:
        conn.close()
    for r in rows:
        rp = r["relpath"]
        if rp in (source_relpath, target_relpath):
            continue
        if links._slugify(rp) == src_slug:
            raise MergeError(
                f"slug {src_slug!r} also names a third page ({rp}); resolve manually")

    # Winner frontmatter = union semantics over target's meta.
    winner_meta = dict(tgt_meta)
    winner_meta["tags"] = _union(tgt_meta.get("tags"), src_meta.get("tags"))
    if not winner_meta["tags"]:
        winner_meta.pop("tags", None)
    for key in links._RELATIONS:
        merged = _union(tgt_meta.get(key), src_meta.get(key))
        if merged:
            winner_meta[key] = merged
    if tgt_meta.get("source_raw") or src_meta.get("source_raw"):
        winner_meta["source_raw"] = _union(
            tgt_meta.get("source_raw"), src_meta.get("source_raw"))
    winner_meta["aliases"] = _union(
        tgt_meta.get("aliases"), [src_slug], src_meta.get("aliases"))

    winner_body = (tgt_body.rstrip() + f"\n\n## Merged from [[{src_slug}]]\n\n"
                   + src_body.strip() + "\n")

    tombstone_meta = dict(src_meta)
    tombstone_meta["status"] = "merged"
    tombstone_meta["merged_into"] = tgt_slug
    tombstone_body = f"> Merged into [[{tgt_slug}]].\n"

    winner_prop = _proposal_path(tgt_abs)
    source_prop = _proposal_path(src_abs)
    winner_prop.write_text(frontmatter.dump(winner_meta, winner_body), encoding="utf-8")
    source_prop.write_text(
        frontmatter.dump(tombstone_meta, tombstone_body), encoding="utf-8")

    return {
        "winner_proposal": str(winner_prop.relative_to(root)),
        "source_proposal": str(source_prop.relative_to(root)),
        "winner_relpath": target_relpath,
        "source_relpath": source_relpath,
        "alias_added": src_slug,
        "status": "staged",
    }


def apply(db_path: Path, *, vault_id: int, winner_proposal: str,
          source_proposal: str) -> dict:
    """Apply staged merge proposals atomically.

    Validates both proposals exist before writing anything.  Writes the winner
    and tombstone, removes the proposals, then runs a full reindex (which calls
    links.resolve internally so [[source-slug]] references resolve to the winner
    via its new aliases entry).
    """
    root = registry.get_vault_root(db_path, vault_id)
    for prop in (winner_proposal, source_proposal):
        if not prop.endswith(".proposed.md"):
            raise MergeError(f"not a proposal path: {prop}")
        if not (root / prop).exists():
            raise MergeError(f"proposal not found: {prop}")
    winner_prop_abs = root / winner_proposal
    source_prop_abs = root / source_proposal
    winner_target = winner_prop_abs.with_name(winner_prop_abs.name[: -len(".proposed.md")])
    source_target = source_prop_abs.with_name(source_prop_abs.name[: -len(".proposed.md")])
    # Atomic: validate both proposals first, then write both, then reindex once.
    winner_target.write_text(winner_prop_abs.read_text(encoding="utf-8"), encoding="utf-8")
    source_target.write_text(source_prop_abs.read_text(encoding="utf-8"), encoding="utf-8")
    winner_prop_abs.unlink()
    source_prop_abs.unlink()
    # reindex.full calls links.resolve internally — no separate resolve call needed.
    reindex.full(db_path, vault_id=vault_id)
    tomb_meta, _ = frontmatter.parse(source_target.read_text(encoding="utf-8"))
    win_meta, _ = frontmatter.parse(winner_target.read_text(encoding="utf-8"))
    return {
        "winner_relpath": str(winner_target.relative_to(root)),
        "source_relpath": str(source_target.relative_to(root)),
        "merged_into": tomb_meta.get("merged_into"),
        "aliases": win_meta.get("aliases", []),
        "status": "applied",
    }
