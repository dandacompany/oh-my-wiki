"""Vault health checks: frontmatter validity (schema-driven) + sqlite↔disk drift."""
from __future__ import annotations

from pathlib import Path

from scripts import frontmatter, links, registry, schema, entity_link
from scripts.paths import registry_path

# Files whose frontmatter is intentionally minimal (no schema check).
_META_RELPATHS = set(links.META_RELPATHS)


def check(db_path: Path, *, vault_id: int) -> dict:
    """Return a categorized report dict. Read-only."""
    root = registry.get_vault_root(db_path, vault_id)
    conn = registry.connect(db_path)
    try:
        rows = list(conn.execute(
            "SELECT relpath, mtime FROM notes WHERE vault_id = ?",
            (vault_id,),
        ))
    finally:
        conn.close()

    fm_issues: list[dict] = []
    missing_files: list[dict] = []
    mtime_drift: list[dict] = []
    status_map: dict[str, str] = {}

    # 1) sqlite rows vs disk
    for row in rows:
        abs_path = root / row["relpath"]
        if not abs_path.exists():
            missing_files.append({"relpath": row["relpath"]})
            continue
        disk_mtime = abs_path.stat().st_mtime
        if abs(disk_mtime - row["mtime"]) > 1.0:
            mtime_drift.append({
                "relpath": row["relpath"],
                "indexed_mtime": row["mtime"],
                "disk_mtime": disk_mtime,
            })

    # 2) disk files (.md, excluding .trash and raw/) — schema-driven frontmatter checks
    schemas, schema_load_errors = schema.load_schemas_with_errors(vault_path=root)
    for md in sorted(root.rglob("*.md")):
        if ".trash" in md.parts or md.name.endswith(".proposed.md"):
            continue
        relpath = str(md.relative_to(root)).replace("\\", "/")
        if relpath in _META_RELPATHS or relpath.startswith("raw/"):
            continue
        text = md.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(text)
        except frontmatter.FrontmatterError as exc:
            fm_issues.append({
                "relpath": relpath,
                "issue": "malformed_yaml",
                "detail": str(exc),
            })
            continue
        for issue in schema.validate(meta, body, schemas=schemas):
            fm_issues.append({"relpath": relpath, **issue})
        if meta.get("status") is not None:
            status_map[relpath] = meta["status"]

    broken = links.broken_links(db_path, vault_id=vault_id)
    orphan_pages = [
        o for o in links.orphans(db_path, vault_id=vault_id)
        if status_map.get(o["relpath"]) != "superseded"
    ]
    index_drift_report = links.index_drift(db_path, vault_id=vault_id)
    contradictions = links.relations(db_path, vault_id=vault_id, relation="contradicts")
    supersedes = links.relations(db_path, vault_id=vault_id, relation="supersedes")
    superseded_unmarked = [
        {"relpath": e["dst_relpath"], "superseded_by_relpath": e["src_relpath"]}
        for e in supersedes
        if e["dst_relpath"] and status_map.get(e["dst_relpath"]) != "superseded"
    ]
    link_suggestions = entity_link.suggest_links(db_path, vault_id=vault_id)

    return {
        "vault_id": vault_id,
        "vault_path": str(root),
        "schema_load_errors": schema_load_errors,
        "frontmatter_issues": fm_issues,
        "drift": {
            "missing_files": missing_files,
            "mtime_drift": mtime_drift,
        },
        "links": {
            "broken": broken,
            "orphans": orphan_pages,
            "index_drift": index_drift_report,
            "contradictions": contradictions,
            "supersedes": supersedes,
            "superseded_unmarked": superseded_unmarked,
            "link_suggestions": link_suggestions,
        },
        "auto_fix_hints": _hints(fm_issues, missing_files, mtime_drift, broken,
                                 orphan_pages, index_drift_report, contradictions,
                                 superseded_unmarked, link_suggestions),
    }


def _hints(fm_issues, missing, drift, broken=None, orphan_pages=None,
           index_drift=None, contradictions=None, superseded_unmarked=None,
           link_suggestions=None) -> list[str]:
    hints = []
    if drift:
        hints.append("Run `reindex.incremental(db, vault_id=...)` to refresh mtime drift.")
    if missing:
        hints.append("Missing files: delete the orphan rows or restore the files.")
    if fm_issues:
        hints.append("Edit each file's YAML frontmatter to fix the reported issues.")
    if any(str(i.get("issue", "")).startswith("missing_section:") for i in fm_issues):
        hints.append("Missing required section(s): add the heading to the page, "
                     "or override the type's schema in <vault>/schemas/.")
    if broken:
        hints.append("Broken links: fix the target slug or create the missing page.")
    if orphan_pages:
        hints.append("Orphan pages: add an inbound link from a related page, or archive.")
    if index_drift and (index_drift.get("missing_from_index") or index_drift.get("dangling_in_index")):
        hints.append("Index drift: run the curator persona (persona-curate-index) to sync wiki/index.md.")
    if contradictions:
        hints.append("Explicit contradictions declared — run the consistency-checker "
                     "persona to adjudicate them.")
    if superseded_unmarked:
        hints.append("Pages superseded by others aren't marked — run "
                     "`omw supersede <relpath> --by <slug>` (or the wiki-auditor) "
                     "to set status: superseded.")
    if link_suggestions:
        hints.append("Unlinked mentions of existing pages — run "
                     "`omw links link <relpath> --to <slug>` (or the curator) to add `[[links]]`.")
    return hints


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    p = argparse.ArgumentParser(description="Lint a registered vault.")
    p.add_argument("--db", default=None)
    p.add_argument("--vault-id", type=int, required=True)
    args = p.parse_args(argv)
    db = Path(args.db) if args.db else registry_path()
    report = check(db, vault_id=args.vault_id)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
