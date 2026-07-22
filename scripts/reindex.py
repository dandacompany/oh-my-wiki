"""Filesystem → sqlite indexer using mtime to skip unchanged files."""
from __future__ import annotations

import argparse
import codecs
import json
import sys
from pathlib import Path

from scripts import embed, frontmatter, fts, links, registry, schema, vector_index


def full(db_path: Path, *, vault_id: int) -> dict:
    """Rescan everything; disk is authoritative. Prunes registry rows whose file
    was deleted on disk. Returns {"indexed": N, "pruned": [relpaths], ...}.

    (Was previously an int of indexed count; callers that only need the count
    read ["indexed"].)"""
    vault_path = registry.get_vault_root(db_path, vault_id)
    return _scan(db_path, vault_id, vault_path, incremental=False)


def incremental(db_path: Path, *, vault_id: int) -> int:
    """Only upsert files whose mtime exceeds the recorded one."""
    vault_path = registry.get_vault_root(db_path, vault_id)
    res = _scan(db_path, vault_id, vault_path, incremental=True)
    changed_wiki = [r for r in res["changed"] if r.startswith("wiki/")]
    if changed_wiki:
        refresh_embeddings(db_path, vault_id=vault_id, relpaths=changed_wiki)
    return res["indexed"]


def refresh_embeddings(db_path: Path, *, vault_id: int, relpaths: list[str] | None = None, strict: bool = False) -> int:
    """Re-embed wiki/ pages for a vault. Best-effort: returns 0 on any error.

    When *relpaths* is given, only embed those wiki/ pages (filtered to wiki/-prefixed ones).
    When *relpaths* is None, embed all wiki/ pages (full-rebuild behaviour).
    """
    try:
        from scripts import config
        cfg = config.load_config()
        emb_cfg = (cfg.get("recall") or {}).get("embedding") or {}
        embedder = embed.get_embedder(emb_cfg)
        if embedder is None or not vector_index.available():
            return 0  # unconfigured — silent no-op
        conn = registry.connect(db_path)
        try:
            if relpaths is not None:
                wiki_relpaths = [r for r in relpaths if r.startswith("wiki/")]
                if not wiki_relpaths:
                    return 0
                placeholders = ",".join("?" * len(wiki_relpaths))
                rows_raw = conn.execute(
                    "SELECT relpath, title, summary FROM notes"
                    f" WHERE vault_id = ? AND parse_error = 0 AND relpath IN ({placeholders})",
                    (vault_id, *wiki_relpaths),
                ).fetchall()
            else:
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
    except Exception as e:
        if strict:
            raise
        print(
            f"warning: embedding refresh failed ({type(e).__name__});"
            " embedding/hybrid recall may use stale vectors",
            file=sys.stderr,
        )
        return 0


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
    changed: list[str] = []
    fts_errors: list[str] = []
    decode_errors: list[str] = []
    seen: set[str] = set()
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
        if path.name.endswith(".proposed.md"):
            continue
        rel = str(path.relative_to(vault_path)).replace("\\", "/")
        seen.add(rel)  # every on-disk .md (even mtime-skipped) — basis for prune
        mtime = path.stat().st_mtime
        if incremental and rel in known and known[rel] >= mtime:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # One mis-encoded note (CP949/EUC-KR, Notepad UTF-16, …) must not
            # abort the whole reindex — and by extension `omw setup`.
            raw, how = _read_text_lenient(path)
            decode_errors.append(rel)
            print(
                f"warning: {rel}: not valid UTF-8 ({how}) — "
                f"convert it to UTF-8 (e.g. iconv) and reindex for a clean index",
                file=sys.stderr,
            )
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
        aliases = meta.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        type_ = meta.get("type")
        status = meta.get("status")
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
            aliases=[str(a) for a in aliases],
            type_=type_,
            status=status,
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
                fts_errors.append(rel)  # FTS is optional; never abort indexing
        if fm_ok and rel not in exempt and not rel.startswith("raw/"):
            issues = schema.validate(meta, body, schemas=schemas)
            if issues:
                schema_issues.append({"relpath": rel, "issues": issues})
        count += 1
        changed.append(rel)
    if fts_conn is not None:
        fts_conn.commit()
        fts_conn.close()
    # On a FULL rescan, disk is authoritative: drop registry rows whose file no
    # longer exists (orphans from a hand-deleted raw/page). FTS was already
    # cleared+repopulated above, so notes is the only place orphans linger. An
    # incremental scan only sees changed files, so its `seen` is partial — never
    # prune there. Files are never touched; this is index-integrity repair, not a
    # page mutation.
    pruned: list[str] = []
    if not incremental:
        for row in registry.list_notes(db_path, vault_id=vault_id):
            if row["relpath"] not in seen:
                registry.delete_note(db_path, vault_id=vault_id, relpath=row["relpath"])
                pruned.append(row["relpath"])
    links.resolve(db_path, vault_id)
    return {"indexed": count, "schema_issues": schema_issues, "changed": changed,
            "fts_errors": fts_errors, "decode_errors": decode_errors, "pruned": pruned}


def _read_text_lenient(path: Path) -> tuple[str, str]:
    """Best-effort decode for a note that is not valid UTF-8.

    A UTF-16 BOM (what Windows Notepad writes) decodes losslessly; anything else
    falls back to UTF-8 with replacement characters so the note is still indexed.
    Returns (text, how) where how describes the recovery for the warning message.
    The file on disk is never modified.
    """
    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16"), "decoded as UTF-16"
    return data.decode("utf-8", errors="replace"), "indexed with replacement characters"


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
    vault_path = registry.get_vault_root(db, args.vault_id)
    result = _scan(db, args.vault_id, vault_path, incremental=not args.full)
    fts_errors = result.get("fts_errors") or []
    if fts_errors:
        print(f"warning: {len(fts_errors)} note(s) failed FTS indexing "
              f"(search may be partial): {', '.join(fts_errors[:5])}"
              f"{' …' if len(fts_errors) > 5 else ''}", file=sys.stderr)
    print(json.dumps({
        "vault_id": args.vault_id,
        "mode": "full" if args.full else "incremental",
        "indexed": result["indexed"],
        "schema_issues": len(result["schema_issues"]),
        "fts_errors": len(fts_errors),
        "decode_errors": len(result.get("decode_errors") or []),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
