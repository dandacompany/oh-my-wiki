"""Filesystem → sqlite indexer using mtime to skip unchanged files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts import embed, frontmatter, fts, links, registry, schema, vector_index


def full(db_path: Path, *, vault_id: int) -> int:
    """Rescan everything. Returns number of notes indexed."""
    vault_path = _vault_path(db_path, vault_id)
    return _scan(db_path, vault_id, vault_path, incremental=False)["indexed"]


def incremental(db_path: Path, *, vault_id: int) -> int:
    """Only upsert files whose mtime exceeds the recorded one."""
    vault_path = _vault_path(db_path, vault_id)
    count = _scan(db_path, vault_id, vault_path, incremental=True)["indexed"]
    try:
        refresh_embeddings(db_path, vault_id=vault_id)
    except Exception:
        pass
    return count


def refresh_embeddings(db_path: Path, *, vault_id: int) -> int:
    """Re-embed all wiki/ pages for a vault. Best-effort: returns 0 on any error."""
    try:
        from scripts import config
        cfg = config.load_config()
        emb_cfg = (cfg.get("recall") or {}).get("embedding") or {}
        embedder = embed.get_embedder(emb_cfg)
        if embedder is None or not vector_index.available():
            return 0
        conn = registry.connect(db_path)
        try:
            rows_raw = conn.execute(
                "SELECT relpath, title, summary FROM notes"
                " WHERE vault_id = ? AND parse_error = 0 AND relpath LIKE 'wiki/%'",
                (vault_id,),
            ).fetchall()
        finally:
            conn.close()
        rows = [
            (r["relpath"], f"{r['title'] or ''} {r['summary'] or ''}".strip())
            for r in rows_raw
        ]
        return vector_index.upsert(db_path, vault_id=vault_id, embedder=embedder, rows=rows)
    except Exception:
        return 0


def _vault_path(db_path: Path, vault_id: int) -> Path:
    conn = registry.connect(db_path)
    try:
        row = conn.execute(
            "SELECT path FROM vaults WHERE id = ?", (vault_id,)
        ).fetchone()
        if not row:
            raise registry.VaultError(f"vault id {vault_id} not found")
        return Path(row[0])
    finally:
        conn.close()


def _existing_mtimes(db_path: Path, vault_id: int) -> dict[str, float]:
    conn = registry.connect(db_path)
    try:
        return {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT relpath, mtime FROM notes WHERE vault_id = ?", (vault_id,)
            )
        }
    finally:
        conn.close()


def _classify_layer(relpath: str) -> str:
    parts = relpath.split("/")
    if parts[0] == "raw":
        return "raw"
    if parts[0] == "wiki":
        if len(parts) == 2 and parts[1] in {"index.md", "log.md"}:
            return "meta"
        return "wiki"
    return "memo"


def _scan(
    db_path: Path,
    vault_id: int,
    vault_path: Path,
    *,
    incremental: bool,
) -> dict:
    registry.init_db(db_path)  # idempotent; guarantees the links table on old vaults
    schemas = schema.load_schemas(vault_path=vault_path)
    exempt = set(links.META_RELPATHS)
    schema_issues: list[dict] = []
    count = 0
    fts_conn = None
    if fts.fts5_available():
        fts_conn = registry.connect(db_path)
        migrated = fts.ensure_fts(fts_conn)
        if migrated:
            incremental = False  # one-time: rebuilt FTS must be fully repopulated
        if not incremental:
            fts.clear_vault(fts_conn, vault_id=vault_id)
        fts_conn.commit()
    known = _existing_mtimes(db_path, vault_id) if incremental else {}
    for path in vault_path.rglob("*.md"):
        if any(part in {".trash", ".obsidian", ".git"} for part in path.parts):
            continue
        rel = str(path.relative_to(vault_path)).replace("\\", "/")
        mtime = path.stat().st_mtime
        if incremental and rel in known and known[rel] >= mtime:
            continue
        raw = path.read_text(encoding="utf-8")
        try:
            meta, body = frontmatter.parse(raw)
            parse_error = False
            fm_ok = True  # frontmatter parsed (even if empty) → schema-validatable, like lint
        except frontmatter.FrontmatterError:
            meta = {}
            body = raw  # still extract links from a frontmatter-broken note
            parse_error = True
            fm_ok = False
        if not meta:
            parse_error = True
        tags = meta.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        note_id = registry.upsert_note(
            db_path,
            vault_id=vault_id,
            relpath=rel,
            layer=_classify_layer(rel),
            title=meta.get("title"),
            summary=meta.get("summary"),
            mtime=mtime,
            size_bytes=path.stat().st_size,
            tags=[str(t) for t in tags],
            parse_error=parse_error,
            visibility=meta.get("visibility") or "private",
        )
        links.replace_links(db_path, vault_id=vault_id, src_note_id=note_id, body=body, meta=meta)
        if fts_conn is not None:
            try:
                fts.index_note(fts_conn, vault_id=vault_id, relpath=rel,
                               title=meta.get("title"), summary=meta.get("summary"),
                               tags=[str(t) for t in tags], body=body,
                               visibility=meta.get("visibility") or "private")
                fts_conn.commit()
            except Exception:
                pass  # FTS is an optional auxiliary index; never abort indexing
        if fm_ok and rel not in exempt and not rel.startswith("raw/"):
            issues = schema.validate(meta, body, schemas=schemas)
            if issues:
                schema_issues.append({"relpath": rel, "issues": issues})
        count += 1
    if fts_conn is not None:
        fts_conn.commit()
        fts_conn.close()
    links.resolve(db_path, vault_id)
    return {"indexed": count, "schema_issues": schema_issues}


def main(argv: list[str] | None = None) -> int:
    """CLI: reindex a vault. Default incremental; --full for a full rescan."""
    from scripts.paths import registry_path
    parser = argparse.ArgumentParser(
        prog="reindex", description="Reindex a vault's notes into the registry."
    )
    parser.add_argument("--vault-id", type=int, required=True)
    parser.add_argument("--db", default=None, help="registry db path (default: ~/.omw/registry.db)")
    parser.add_argument("--full", action="store_true", help="full rescan (default: incremental)")
    args = parser.parse_args(argv)
    db = Path(args.db) if args.db else registry_path()
    vault_path = _vault_path(db, args.vault_id)
    result = _scan(db, args.vault_id, vault_path, incremental=not args.full)
    print(json.dumps({
        "vault_id": args.vault_id,
        "mode": "full" if args.full else "incremental",
        "indexed": result["indexed"],
        "schema_issues": len(result["schema_issues"]),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
