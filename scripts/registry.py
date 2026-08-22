"""sqlite-backed registry for oh-my-wiki vaults and notes."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 5
SCHEMA_SQL_PATH = Path(__file__).parent / "db" / "schema.sql"
DEFAULT_BUSY_TIMEOUT_MS = 30_000


def _writer_path(db_path: Path) -> Path:
    return Path(f"{db_path}.writer.json")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _writer_detail(db_path: Path) -> str:
    """Best-effort owner hint for an OMW-managed write transaction."""
    marker = _writer_path(db_path)
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        pid = int(data.get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return "writer PID unavailable"
    if not _pid_alive(pid):
        try:
            marker.unlink()
        except OSError:
            pass
        return f"stale writer PID {pid}"
    return f"writer PID {pid}"


class RegistryConnection(sqlite3.Connection):
    """Connection that records the current OMW writer for lock diagnostics."""

    _db_path: Path
    _owns_writer_marker: bool

    def _mark_write(self, sql: str) -> None:
        first = (sql or "").lstrip().split(None, 1)[0].upper() if (sql or "").strip() else ""
        if first not in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "ALTER", "DROP"}:
            return
        if getattr(self, "_owns_writer_marker", False):
            return
        marker = _writer_path(self._db_path)
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # A live marker belongs to the writer ahead of us. A dead marker is
            # cleaned by _writer_detail and can be claimed on the next attempt.
            _writer_detail(self._db_path)
            return
        except OSError:
            return
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "started_at": time.time()}, stream)
            self._owns_writer_marker = True
        except OSError:
            pass

    def _clear_writer(self) -> None:
        if not getattr(self, "_owns_writer_marker", False):
            return
        marker = _writer_path(self._db_path)
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            if int(data.get("pid") or 0) == os.getpid():
                marker.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self._owns_writer_marker = False

    def _locked(self, exc: sqlite3.OperationalError) -> sqlite3.OperationalError:
        if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
            return exc
        return sqlite3.OperationalError(f"{exc} ({_writer_detail(self._db_path)})")

    def execute(self, sql, parameters=(), /):
        self._mark_write(sql)
        try:
            return super().execute(sql, parameters)
        except sqlite3.OperationalError as exc:
            raise self._locked(exc) from exc

    def executemany(self, sql, seq_of_parameters, /):
        self._mark_write(sql)
        try:
            return super().executemany(sql, seq_of_parameters)
        except sqlite3.OperationalError as exc:
            raise self._locked(exc) from exc

    def executescript(self, sql_script, /):
        self._mark_write(sql_script)
        try:
            return super().executescript(sql_script)
        except sqlite3.OperationalError as exc:
            raise self._locked(exc) from exc

    def commit(self):
        try:
            return super().commit()
        finally:
            self._clear_writer()

    def rollback(self):
        try:
            return super().rollback()
        finally:
            self._clear_writer()

    def close(self):
        try:
            return super().close()
        finally:
            self._clear_writer()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self._clear_writer()


def connect(db_path: Path, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    db_path = Path(db_path)
    conn = sqlite3.connect(
        db_path,
        timeout=max(0, busy_timeout_ms) / 1000,
        factory=RegistryConnection,
    )
    conn._db_path = db_path
    conn._owns_writer_marker = False
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {max(0, int(busy_timeout_ms))}")
    if _migration_needed(conn):
        _migrate_existing(conn)
    return conn


def _migration_needed(conn: sqlite3.Connection) -> bool:
    """Cheap read-only check; avoid taking a write lock on every normal read."""
    names = {
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "vaults" in names:
        vault_cols = {r["name"] for r in conn.execute("PRAGMA table_info(vaults)")}
        if (
            "archived_at" not in vault_cols
            or "session_captures" not in names
            or "knowledge_candidate_batches" not in names
            or "knowledge_candidates" not in names
            or "knowledge_candidate_processed" not in names
            or "knowledge_candidate_scope_modes" not in names
        ):
            return True
        batch_cols = {
            r["name"] for r in conn.execute(
                "PRAGMA table_info(knowledge_candidate_batches)"
            )
        } if "knowledge_candidate_batches" in names else set()
        processed_cols = {
            r["name"] for r in conn.execute(
                "PRAGMA table_info(knowledge_candidate_processed)"
            )
        } if "knowledge_candidate_processed" in names else set()
        if "expired_at" not in batch_cols or "reason" not in processed_cols:
            return True
    if "notes" in names:
        note_cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}
        if not {"visibility", "aliases", "type", "status"}.issubset(note_cols):
            return True
    return False


def _ensure_vault_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add vaults columns introduced after a DB was first created.
    Guard on pragma table_info (SQLite lacks ADD COLUMN IF NOT EXISTS).
    The inner _add helper also swallows duplicate-column errors from races."""
    def _add(sql: str) -> None:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(vaults)")}
    if "archived_at" not in cols:
        _add("ALTER TABLE vaults ADD COLUMN archived_at TEXT")


def _ensure_note_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add columns introduced after a vault's DB was first created.
    SQLite has no ADD COLUMN IF NOT EXISTS, so guard on pragma table_info.
    The inner _add helper also swallows duplicate-column errors from races."""
    def _add(sql: str) -> None:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(notes)")}
    if "visibility" not in cols:
        _add(
            "ALTER TABLE notes ADD COLUMN visibility TEXT NOT NULL "
            "DEFAULT 'private' CHECK (visibility IN ('public', 'private'))"
        )
    if "aliases" not in cols:
        _add("ALTER TABLE notes ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
    if "type" not in cols:
        _add("ALTER TABLE notes ADD COLUMN type TEXT")
    if "status" not in cols:
        _add("ALTER TABLE notes ADD COLUMN status TEXT")


def _ensure_session_capture_table(conn: sqlite3.Connection) -> None:
    """Create the local staged-session table for databases made before v4."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS session_captures (
          id             INTEGER PRIMARY KEY,
          vault_id       INTEGER REFERENCES vaults(id) ON DELETE SET NULL,
          project_root   TEXT NOT NULL,
          host           TEXT NOT NULL,
          session_id     TEXT NOT NULL,
          source         TEXT NOT NULL CHECK (source IN ('stop', 'precompact')),
          captured_at    TEXT NOT NULL,
          content_hash   TEXT NOT NULL,
          last_user      TEXT,
          last_assistant TEXT,
          files          TEXT NOT NULL DEFAULT '[]',
          status         TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'dismissed')),
          UNIQUE(host, session_id, source, content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_session_captures_project
          ON session_captures(project_root, status, id DESC);
        """
    )


def _ensure_candidate_tables(conn: sqlite3.Connection) -> None:
    """Create v5 candidate staging tables without changing capture row shape."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_candidate_batches (
          id INTEGER PRIMARY KEY,
          vault_id INTEGER REFERENCES vaults(id) ON DELETE SET NULL,
          project_root TEXT NOT NULL,
          host TEXT NOT NULL,
          session_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          mode TEXT NOT NULL CHECK (mode IN ('staged', 'auto-raw')),
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved', 'dismissed')),
          raw_relpath TEXT,
          expired_at TEXT,
          UNIQUE(vault_id, project_root, session_id, content_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_candidate_batches_status
          ON knowledge_candidate_batches(project_root, status, id DESC);
        CREATE TABLE IF NOT EXISTS knowledge_candidates (
          id INTEGER PRIMARY KEY,
          batch_id INTEGER NOT NULL REFERENCES knowledge_candidate_batches(id)
            ON DELETE CASCADE,
          ordinal INTEGER NOT NULL,
          kind TEXT NOT NULL
            CHECK (kind IN ('decision', 'preference', 'fact', 'procedure', 'incident')),
          classification TEXT NOT NULL
            CHECK (classification IN ('new', 'update', 'duplicate', 'conflict', 'discard')),
          confidence REAL NOT NULL,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          reason TEXT NOT NULL,
          matched_relpath TEXT,
          provenance TEXT NOT NULL DEFAULT '{}',
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved', 'dismissed')),
          UNIQUE(batch_id, ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_candidates_batch_status
          ON knowledge_candidates(batch_id, status, ordinal);
        CREATE TABLE IF NOT EXISTS knowledge_candidate_processed (
          capture_id INTEGER PRIMARY KEY REFERENCES session_captures(id) ON DELETE CASCADE,
          processed_at TEXT NOT NULL,
          outcome TEXT NOT NULL CHECK (outcome IN ('staged', 'discarded')),
          reason TEXT NOT NULL DEFAULT '',
          batch_id INTEGER REFERENCES knowledge_candidate_batches(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge_candidate_scope_modes (
          scope_type TEXT NOT NULL CHECK (scope_type IN ('project', 'host', 'vault')),
          scope_value TEXT NOT NULL,
          mode TEXT NOT NULL CHECK (mode IN ('off', 'advisory', 'staged', 'auto-raw')),
          updated_at TEXT NOT NULL,
          PRIMARY KEY (scope_type, scope_value)
        );
        """
    )
    batch_cols = {
        row["name"] for row in conn.execute(
            "PRAGMA table_info(knowledge_candidate_batches)"
        )
    }
    if "expired_at" not in batch_cols:
        conn.execute("ALTER TABLE knowledge_candidate_batches ADD COLUMN expired_at TEXT")
    processed_cols = {
        row["name"] for row in conn.execute(
            "PRAGMA table_info(knowledge_candidate_processed)"
        )
    }
    if "reason" not in processed_cols:
        conn.execute(
            "ALTER TABLE knowledge_candidate_processed "
            "ADD COLUMN reason TEXT NOT NULL DEFAULT ''"
        )


def _migrate_existing(conn: sqlite3.Connection) -> None:
    """Apply idempotent column migrations to tables that already exist, so every
    connection self-heals a DB created by an older schema version (read paths like
    list_vaults/doctor must not fail on a missing column when init_db wasn't re-run
    after an upgrade). Skips tables that don't exist yet (fresh-DB init order)."""
    names = {r["name"] for r in
             conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "vaults" in names:
        _ensure_vault_columns(conn)
    if "notes" in names:
        _ensure_note_columns(conn)
    if "vaults" in names:
        _ensure_session_capture_table(conn)
        _ensure_candidate_tables(conn)
    conn.commit()


def init_db(db_path: Path) -> None:
    """Create schema if absent. Idempotent."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA_SQL_PATH.read_text()
    conn = connect(db_path)
    try:
        # Set once during explicit initialization. Reissuing journal_mode on every
        # connection can itself wait for a writer and turn a read hook into a write.
        mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        if mode != "wal":
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(sql)
        _ensure_note_columns(conn)
        _ensure_vault_columns(conn)
        _ensure_session_capture_table(conn)
        _ensure_candidate_tables(conn)
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


def get_vault_by_id(db_path: Path, vault_id: int) -> sqlite3.Row | None:
    conn = connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM vaults WHERE id = ?", (vault_id,)
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


def _hand_over_active(conn) -> str | None:
    """If no vault is active, promote the most recently used non-archived one.

    Call inside the caller's transaction, AFTER the row has been removed or archived.
    Returns the new active vault's name, or None when nothing was promoted (either an
    active vault still exists, or no eligible vault remains).

    Why this lives here: `vault forget`, `vault archive`, and `vault delete` (soft and
    hard) all funnel into forget_vault/set_archived, so one implementation closes all
    three. Leaving `active` empty breaks every subsequent command even though other
    vaults are still registered.
    """
    if conn.execute("SELECT 1 FROM vaults WHERE is_active = 1").fetchone():
        return None
    row = conn.execute(
        "SELECT id, name FROM vaults WHERE archived_at IS NULL "
        "ORDER BY last_used DESC, id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    conn.execute("UPDATE vaults SET is_active = 1 WHERE id = ?", (row["id"],))
    return row["name"]


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
                _hand_over_active(conn)
            else:
                conn.execute(
                    "UPDATE vaults SET archived_at = NULL WHERE id = ?", (row["id"],)
                )
        return conn.execute("SELECT * FROM vaults WHERE id = ?", (row["id"],)).fetchone()
    finally:
        conn.close()


def forget_vault(db_path: Path, name: str) -> dict:
    """Remove a vault from the registry. Returns {"active_moved_to": name | None}.

    Previously returned None and silently left `active` empty when the removed vault
    was the active one; callers surface active_moved_to so the move is never silent.
    """
    conn = connect(db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM vaults WHERE name = ?", (name,))
            if cur.rowcount == 0:
                raise VaultError(f"vault {name!r} not found")
            moved = _hand_over_active(conn)
        return {"active_moved_to": moved}
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
            sets.append("mode = ?")
            params.append(mode)
        if config_json is not None:
            sets.append("config_json = ?")
            params.append(config_json)
        if not sets:
            raise VaultError("nothing to update")
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
