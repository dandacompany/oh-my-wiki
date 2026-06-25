"""sqlite-backed registry for oh-my-wiki vaults and notes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 3
SCHEMA_SQL_PATH = Path(__file__).parent / "db" / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_vault_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add vaults columns introduced after a DB was first created.
    Guard on pragma table_info (SQLite lacks ADD COLUMN IF NOT EXISTS)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(vaults)")}
    if "archived_at" not in cols:
        conn.execute("ALTER TABLE vaults ADD COLUMN archived_at TEXT")


def _ensure_note_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add columns introduced after a vault's DB was first created.
    SQLite has no ADD COLUMN IF NOT EXISTS, so guard on pragma table_info."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}
    if "visibility" not in cols:
        conn.execute(
            "ALTER TABLE notes ADD COLUMN visibility TEXT NOT NULL "
            "DEFAULT 'private' CHECK (visibility IN ('public', 'private'))"
        )
    if "aliases" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
    if "type" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN type TEXT")
    if "status" not in cols:
        conn.execute("ALTER TABLE notes ADD COLUMN status TEXT")


def init_db(db_path: Path) -> None:
    """Create schema if absent. Idempotent."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA_SQL_PATH.read_text()
    conn = connect(db_path)
    try:
        conn.executescript(sql)
        _ensure_note_columns(conn)
        _ensure_vault_columns(conn)
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


def list_vaults(db_path: Path, include_archived: bool = False) -> list[sqlite3.Row]:
    conn = connect(db_path)
    try:
        sql = "SELECT * FROM vaults"
        if not include_archived:
            sql += " WHERE archived_at IS NULL"
        sql += " ORDER BY last_used DESC"
        return list(conn.execute(sql))
    finally:
        conn.close()


def get_vault_by_name(db_path: Path, name: str) -> sqlite3.Row | None:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM vaults WHERE name = ?", (name,)
        ).fetchone()
    finally:
        conn.close()


def get_vault_root(db_path: Path, vault_id: int) -> Path:
    """Return a vault's content root by id. Raises VaultError if the id is unknown.
    Single source of truth for the `SELECT path FROM vaults WHERE id=?` lookup."""
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT path FROM vaults WHERE id = ?", (vault_id,)).fetchone()
        if not row:
            raise VaultError(f"vault id {vault_id} not found")
        return Path(row[0])
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


def set_archived(db_path: Path, name: str, archived: bool) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT id FROM vaults WHERE name = ?", (name,)).fetchone()
        if not row:
            raise VaultError(f"vault {name!r} not found")
        ts = _now() if archived else None
        with conn:
            if archived:
                conn.execute(
                    "UPDATE vaults SET archived_at = ?, is_active = 0 WHERE id = ?",
                    (ts, row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE vaults SET archived_at = NULL WHERE id = ?", (row["id"],)
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


def rename_vault(db_path: Path, old: str, new: str) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT id FROM vaults WHERE name = ?", (old,)).fetchone()
        if not row:
            raise VaultError(f"vault {old!r} not found")
        try:
            with conn:
                conn.execute("UPDATE vaults SET name = ? WHERE id = ?", (new, row["id"]))
        except sqlite3.IntegrityError as exc:
            raise VaultError(f"vault name {new!r} is already registered") from exc
        return conn.execute("SELECT * FROM vaults WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()


def update_path(db_path: Path, name: str, new_path: Path) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT id FROM vaults WHERE name = ?", (name,)).fetchone()
        if not row:
            raise VaultError(f"vault {name!r} not found")
        try:
            with conn:
                conn.execute("UPDATE vaults SET path = ? WHERE id = ?",
                             (str(Path(new_path).resolve()), row["id"]))
        except sqlite3.IntegrityError as exc:
            raise VaultError(f"vault path {new_path!r} is already registered") from exc
        return conn.execute("SELECT * FROM vaults WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()


def update_mode_config(db_path: Path, name: str, *,
                       mode: str | None = None,
                       config_json: str | None = None) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT id FROM vaults WHERE name = ?", (name,)).fetchone()
        if not row:
            raise VaultError(f"vault {name!r} not found")
        sets, params = [], []
        if mode is not None:
            sets.append("mode = ?"); params.append(mode)
        if config_json is not None:
            sets.append("config_json = ?"); params.append(config_json)
        params.append(row["id"])
        with conn:
            conn.execute(f"UPDATE vaults SET {', '.join(sets)} WHERE id = ?", params)
        return conn.execute("SELECT * FROM vaults WHERE id = ?", (row["id"],)).fetchone()
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
    visibility: str = "private",
    aliases: list[str] | None = None,
    type_: str | None = None,
    status: str | None = None,
) -> int:
    if visibility not in ("public", "private"):
        visibility = "private"
    aliases_json = json.dumps([str(a) for a in (aliases or [])], ensure_ascii=False)
    conn = connect(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO notes(vault_id, relpath, layer, title, summary,
                                  mtime, size_bytes, parse_error, visibility, aliases,
                                  type, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vault_id, relpath) DO UPDATE SET
                    layer       = excluded.layer,
                    title       = excluded.title,
                    summary     = excluded.summary,
                    mtime       = excluded.mtime,
                    size_bytes  = excluded.size_bytes,
                    parse_error = excluded.parse_error,
                    visibility  = excluded.visibility,
                    aliases     = excluded.aliases,
                    type        = excluded.type,
                    status      = excluded.status
                """,
                (vault_id, relpath, layer, title, summary,
                 mtime, size_bytes, 1 if parse_error else 0, visibility, aliases_json,
                 type_, status),
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


def list_notes_faceted(
    db_path: Path,
    *,
    vault_id: int,
    tag: str | None = None,
    type_: str | None = None,
    status: str | None = None,
    layer: str | None = None,
    visibility: str | None = None,
) -> list[sqlite3.Row]:
    """Faceted note listing. Filters AND together; a None facet is ignored.
    `tag` filters via the note_tags/tags join; the rest are notes columns."""
    where = ["n.vault_id = ?"]
    params: list = [vault_id]
    join = ""
    if tag is not None:
        join = ("JOIN note_tags nt ON nt.note_id = n.id "
                "JOIN tags t ON t.id = nt.tag_id")
        where.append("t.name = ?")
        params.append(tag)
    for col, val in (("type", type_), ("status", status),
                     ("layer", layer), ("visibility", visibility)):
        if val is not None:
            where.append(f"n.{col} = ?")
            params.append(val)
    sql = (f"SELECT DISTINCT n.* FROM notes n {join} "
           f"WHERE {' AND '.join(where)} ORDER BY n.relpath")
    conn = connect(db_path)
    try:
        return list(conn.execute(sql, params))
    finally:
        conn.close()


def note_layer_counts(db_path: Path, vault_id: int) -> dict[str, int]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT layer, COUNT(*) AS n FROM notes WHERE vault_id = ? GROUP BY layer",
            (vault_id,),
        )
        return {r["layer"]: r["n"] for r in rows}
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
