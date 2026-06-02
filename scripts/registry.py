"""sqlite-backed registry for oh-my-wiki vaults and notes."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 2
SCHEMA_SQL_PATH = Path(__file__).parent / "db" / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_note_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add columns introduced after a vault's DB was first created.
    SQLite has no ADD COLUMN IF NOT EXISTS, so guard on pragma table_info."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}
    if "visibility" not in cols:
        conn.execute(
            "ALTER TABLE notes ADD COLUMN visibility TEXT NOT NULL "
            "DEFAULT 'private' CHECK (visibility IN ('public', 'private'))"
        )


def init_db(db_path: Path) -> None:
    """Create schema if absent. Idempotent."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA_SQL_PATH.read_text()
    conn = connect(db_path)
    try:
        conn.executescript(sql)
        _ensure_note_columns(conn)
        existing = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now()),
            )
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class VaultError(Exception):
    """Raised on invalid vault operations."""


def add_vault(
    db_path: Path,
    *,
    name: str,
    path: Path,
    type_: str,
    mode: str,
    config_json: str | None = None,
) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        now = _now()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO vaults(name, path, type, mode, is_active,
                                       created_at, last_used, config_json)
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (name, str(Path(path).resolve()), type_, mode, now, now, config_json),
                )
                return conn.execute(
                    "SELECT * FROM vaults WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            msg = str(exc).lower()
            if "vaults.name" in msg:
                raise VaultError(f"vault name {name!r} is already registered") from exc
            if "vaults.path" in msg:
                raise VaultError(f"vault path {path!r} is already registered") from exc
            raise VaultError(str(exc)) from exc
    finally:
        conn.close()


def list_vaults(db_path: Path) -> list[sqlite3.Row]:
    conn = connect(db_path)
    try:
        return list(conn.execute("SELECT * FROM vaults ORDER BY last_used DESC"))
    finally:
        conn.close()


def get_active(db_path: Path) -> sqlite3.Row | None:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM vaults WHERE is_active = 1"
        ).fetchone()
    finally:
        conn.close()


def set_active(db_path: Path, name: str) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM vaults WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            raise VaultError(f"vault {name!r} not found")
        with conn:
            conn.execute("UPDATE vaults SET is_active = 0 WHERE is_active = 1")
            conn.execute(
                "UPDATE vaults SET is_active = 1, last_used = ? WHERE id = ?",
                (_now(), row["id"]),
            )
        return conn.execute("SELECT * FROM vaults WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()


def forget_vault(db_path: Path, name: str) -> None:
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM vaults WHERE name = ?", (name,))
            if cur.rowcount == 0:
                raise VaultError(f"vault {name!r} not found")
    finally:
        conn.close()


def upsert_note(
    db_path: Path,
    *,
    vault_id: int,
    relpath: str,
    layer: str,
    title: str | None,
    summary: str | None,
    mtime: float,
    size_bytes: int,
    tags: list[str],
    parse_error: bool = False,
) -> int:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO notes(vault_id, relpath, layer, title, summary,
                                  mtime, size_bytes, parse_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vault_id, relpath) DO UPDATE SET
                    layer       = excluded.layer,
                    title       = excluded.title,
                    summary     = excluded.summary,
                    mtime       = excluded.mtime,
                    size_bytes  = excluded.size_bytes,
                    parse_error = excluded.parse_error
                """,
                (vault_id, relpath, layer, title, summary,
                 mtime, size_bytes, 1 if parse_error else 0),
            )
            note_id = conn.execute(
                "SELECT id FROM notes WHERE vault_id = ? AND relpath = ?",
                (vault_id, relpath),
            ).fetchone()["id"]
            _replace_note_tags(conn, note_id, tags)
        return note_id
    finally:
        conn.close()


def _replace_note_tags(conn: sqlite3.Connection, note_id: int, tags: list[str]) -> None:
    conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
    for tag in tags:
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
        tag_id = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag,)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO note_tags(note_id, tag_id) VALUES (?, ?)",
            (note_id, tag_id),
        )


def list_notes(
    db_path: Path,
    *,
    vault_id: int,
    layer: str | None = None,
) -> list[sqlite3.Row]:
    conn = connect(db_path)
    try:
        if layer:
            return list(conn.execute(
                "SELECT * FROM notes WHERE vault_id = ? AND layer = ? ORDER BY relpath",
                (vault_id, layer),
            ))
        return list(conn.execute(
            "SELECT * FROM notes WHERE vault_id = ? ORDER BY relpath",
            (vault_id,),
        ))
    finally:
        conn.close()


def delete_note(db_path: Path, *, vault_id: int, relpath: str) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                "DELETE FROM notes WHERE vault_id = ? AND relpath = ?",
                (vault_id, relpath),
            )
    finally:
        conn.close()


def get_tags_for_note(db_path: Path, note_id: int) -> list[str]:
    conn = connect(db_path)
    try:
        return [
            row["name"]
            for row in conn.execute(
                """
                SELECT t.name FROM tags t
                JOIN note_tags nt ON nt.tag_id = t.id
                WHERE nt.note_id = ?
                ORDER BY t.name
                """,
                (note_id,),
            )
        ]
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import sys

    from scripts.paths import registry_path

    p = argparse.ArgumentParser(prog="registry")
    sub = p.add_subparsers(dest="cmd", required=True)
    pv = sub.add_parser("vaults", help="List registered vaults as JSON.")
    pv.add_argument("--db", default=None)
    args = p.parse_args(argv)

    if args.cmd == "vaults":
        db = Path(args.db) if args.db else registry_path()
        rows = list_vaults(db) if db.exists() else []
        out = [
            {
                "id": v["id"],
                "name": v["name"],
                "path": v["path"],
                "mode": v["mode"],
                "type": v["type"],
                "is_active": bool(v["is_active"]),
            }
            for v in rows
        ]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    return 1


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
