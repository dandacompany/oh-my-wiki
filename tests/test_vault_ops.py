import json as _json
import sqlite3
from pathlib import Path

import pytest

from scripts import omw_cli, registry, vault_ops


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


# --- Task 2 tests ---


def test_info_returns_card_with_layer_counts(tmp_path):
    db = _fresh_db(tmp_path)
    vault = registry.add_vault(db, name="v1", path=tmp_path / "v1",
                               type_="markdown", mode="wiki")
    registry.upsert_note(db, vault_id=vault["id"], relpath="raw/a.md",
                         layer="raw", title="A", summary=None, mtime=1.0,
                         size_bytes=10, tags=[])
    registry.upsert_note(db, vault_id=vault["id"], relpath="wiki/b.md",
                         layer="wiki", title="B", summary=None, mtime=1.0,
                         size_bytes=10, tags=[])
    card = vault_ops.info(db, "v1")
    assert card["name"] == "v1"
    assert card["type"] == "markdown"
    assert card["mode"] == "wiki"
    assert card["archived"] is False
    assert card["note_counts"] == {"raw": 1, "wiki": 1}
    assert card["total_notes"] == 2


def test_info_unknown_vault_raises(tmp_path):
    db = _fresh_db(tmp_path)
    with pytest.raises(registry.VaultError):
        vault_ops.info(db, "nope")


def test_current_returns_active_row(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    registry.set_active(db, "v1")
    row = vault_ops.current(db)
    assert row["name"] == "v1"


def test_current_no_active_returns_none(tmp_path):
    db = _fresh_db(tmp_path)
    assert vault_ops.current(db) is None


def test_cli_vault_info_outputs_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts.paths import registry_path
    registry.init_db(registry_path())
    registry.add_vault(registry_path(), name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    assert omw_cli.main(["vault", "info", "v1"]) == 0
    out = _json.loads(capsys.readouterr().out)
    assert out["name"] == "v1"
