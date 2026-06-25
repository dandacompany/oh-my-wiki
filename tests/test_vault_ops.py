import sqlite3
from pathlib import Path

from scripts import registry


def _fresh_db(tmp_path: Path) -> Path:
    db = tmp_path / "registry.db"
    registry.init_db(db)
    return db


def test_archived_at_column_exists_and_defaults_null(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    row = registry.get_vault_by_name(db, "v1")
    assert "archived_at" in row.keys()
    assert row["archived_at"] is None


def test_list_vaults_hides_archived_by_default(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="a", path=tmp_path / "a",
                       type_="markdown", mode="wiki")
    registry.add_vault(db, name="b", path=tmp_path / "b",
                       type_="markdown", mode="wiki")
    # Manually archive 'b' via direct SQL (set_archived comes in Task 6).
    conn = registry.connect(db)
    with conn:
        conn.execute("UPDATE vaults SET archived_at = '2026-06-25T00:00:00+00:00' "
                     "WHERE name = 'b'")
    conn.close()
    default_names = {v["name"] for v in registry.list_vaults(db)}
    all_names = {v["name"] for v in registry.list_vaults(db, include_archived=True)}
    assert default_names == {"a"}
    assert all_names == {"a", "b"}


def test_migration_adds_archived_at_to_v2_db(tmp_path):
    # Simulate a pre-migration vaults table (no archived_at), then migrate.
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
        "CREATE TABLE vaults (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, "
        "path TEXT NOT NULL UNIQUE, type TEXT NOT NULL, mode TEXT NOT NULL, "
        "is_active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, "
        "last_used TEXT NOT NULL, config_json TEXT);"
        "INSERT INTO vaults(name, path, type, mode, created_at, last_used) "
        "VALUES ('legacy', '/tmp/legacy', 'markdown', 'wiki', 'x', 'x');"
    )
    conn.commit()
    conn.close()
    registry.init_db(db)  # should add the column without dropping the row
    row = registry.get_vault_by_name(db, "legacy")
    assert row is not None
    assert "archived_at" in row.keys()
    assert row["archived_at"] is None
