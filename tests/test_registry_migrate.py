"""Tests for connect() auto-migration: self-healing old-schema DBs."""
import sqlite3

from scripts import registry


def test_connect_automigrates_pre3_vaults(tmp_path):
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    # OLD vaults schema WITHOUT archived_at (pre SCHEMA_VERSION 3)
    c.execute(
        "CREATE TABLE vaults (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
        "path TEXT NOT NULL UNIQUE, type TEXT, mode TEXT, is_active INTEGER DEFAULT 0, "
        "created_at TEXT, last_used TEXT, config_json TEXT)"
    )
    c.execute(
        "INSERT INTO vaults(name,path,type,mode,created_at,last_used) "
        "VALUES ('v','/tmp/v','markdown','wiki','t','t')"
    )
    c.commit()
    c.close()

    # Must NOT raise 'no such column: archived_at'
    rows = registry.list_vaults(db)
    assert [r["name"] for r in rows] == ["v"]

    conn = registry.connect(db)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(vaults)")}
        assert "archived_at" in cols
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "session_captures" in tables
    finally:
        conn.close()


def test_connect_automigrates_pre_note_columns(tmp_path):
    db = tmp_path / "oldnotes.db"
    c = sqlite3.connect(db)
    # OLD notes table missing visibility/aliases/type/status
    c.execute(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY, vault_id INTEGER, relpath TEXT, "
        "title TEXT, summary TEXT, parse_error INTEGER DEFAULT 0)"
    )
    c.commit()
    c.close()

    cols = {r["name"] for r in registry.connect(db).execute("PRAGMA table_info(notes)")}
    assert {"visibility", "aliases", "type", "status"} <= cols


def test_connect_on_fresh_db_is_noop(tmp_path):
    # brand-new empty DB: connect must not error (no tables to migrate)
    conn = registry.connect(tmp_path / "fresh.db")
    assert conn is not None
    conn.close()
