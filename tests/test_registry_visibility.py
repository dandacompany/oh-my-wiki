# tests/test_registry_visibility.py
import sqlite3
from pathlib import Path

from scripts import registry


def _columns(db, table):
    conn = registry.connect(db)
    try:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_fresh_db_has_visibility_column(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    assert "visibility" in _columns(db, "notes")


def test_migration_adds_visibility_to_old_notes_table(tmp_path):
    # Simulate a pre-visibility DB: create the notes table WITHOUT the column.
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE vaults (id INTEGER PRIMARY KEY, name TEXT, path TEXT,
            type TEXT, mode TEXT, is_active INTEGER DEFAULT 0,
            created_at TEXT, last_used TEXT, config_json TEXT);
        CREATE TABLE notes (id INTEGER PRIMARY KEY, vault_id INTEGER, relpath TEXT,
            layer TEXT, title TEXT, summary TEXT, mtime REAL, size_bytes INTEGER,
            parse_error INTEGER DEFAULT 0, UNIQUE(vault_id, relpath));
        INSERT INTO notes(vault_id, relpath, layer, title, summary, mtime, size_bytes)
            VALUES (1, 'wiki/a.md', 'wiki', 'A', 's', 1.0, 10);
        """
    )
    conn.commit()
    conn.close()

    registry.init_db(db)  # must migrate in place, not raise

    conn = registry.connect(db)
    try:
        assert "visibility" in _columns(db, "notes")
        row = conn.execute("SELECT visibility FROM notes WHERE relpath='wiki/a.md'").fetchone()
        assert row["visibility"] == "private"  # existing rows default to private
    finally:
        conn.close()


def _visibility(db):
    conn = registry.connect(db)
    try:
        return conn.execute(
            "SELECT visibility FROM notes WHERE relpath='wiki/a.md'"
        ).fetchone()["visibility"]
    finally:
        conn.close()


def test_upsert_note_defaults_private(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    registry.add_vault(db, name="v", path=Path(tmp_path / "v"), type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    registry.upsert_note(db, vault_id=vid, relpath="wiki/a.md", layer="wiki",
                         title="A", summary="s", mtime=1.0, size_bytes=10, tags=[])
    assert _visibility(db) == "private"


def test_upsert_note_stores_and_updates_visibility(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    registry.add_vault(db, name="v", path=Path(tmp_path / "v"), type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    registry.upsert_note(db, vault_id=vid, relpath="wiki/a.md", layer="wiki",
                         title="A", summary="s", mtime=1.0, size_bytes=10, tags=[],
                         visibility="public")
    # The INSERT path must store the requested visibility verbatim.
    assert _visibility(db) == "public"
    # ON CONFLICT path must also update visibility back to private.
    # Keep mtime/size_bytes identical so only `visibility` differs.
    registry.upsert_note(db, vault_id=vid, relpath="wiki/a.md", layer="wiki",
                         title="A", summary="s", mtime=1.0, size_bytes=10, tags=[],
                         visibility="private")
    assert _visibility(db) == "private"


def test_upsert_note_invalid_visibility_falls_back_to_private(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    registry.add_vault(db, name="v", path=Path(tmp_path / "v"), type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    registry.upsert_note(db, vault_id=vid, relpath="wiki/a.md", layer="wiki",
                         title="A", summary="s", mtime=1.0, size_bytes=10, tags=[],
                         visibility="internal")  # not a valid value
    assert _visibility(db) == "private"
