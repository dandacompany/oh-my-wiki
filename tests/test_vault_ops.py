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


def test_rename_changes_name_preserving_id(tmp_path):
    db = _fresh_db(tmp_path)
    v = registry.add_vault(db, name="old", path=tmp_path / "old",
                           type_="markdown", mode="wiki")
    vault_ops.rename(db, "old", "new")
    assert registry.get_vault_by_name(db, "old") is None
    row = registry.get_vault_by_name(db, "new")
    assert row["id"] == v["id"]


def test_rename_to_existing_name_rejected(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="a", path=tmp_path / "a",
                       type_="markdown", mode="wiki")
    registry.add_vault(db, name="b", path=tmp_path / "b",
                       type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError):
        vault_ops.rename(db, "a", "b")


def test_rename_unknown_rejected(tmp_path):
    db = _fresh_db(tmp_path)
    with pytest.raises(registry.VaultError):
        vault_ops.rename(db, "ghost", "x")


def test_move_relocates_folder_and_updates_path(tmp_path):
    db = _fresh_db(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "marker.md").write_text("hi")
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    dst = tmp_path / "dst"
    vault_ops.move(db, "v1", str(dst))
    assert not src.exists()
    assert (dst / "marker.md").read_text() == "hi"
    row = registry.get_vault_by_name(db, "v1")
    assert Path(row["path"]) == dst.resolve()


def test_move_to_occupied_target_rejected(tmp_path):
    db = _fresh_db(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    dst = tmp_path / "dst"
    dst.mkdir()  # already exists
    with pytest.raises(registry.VaultError):
        vault_ops.move(db, "v1", str(dst))
    # row unchanged, source intact
    assert src.exists()
    assert Path(registry.get_vault_by_name(db, "v1")["path"]) == src.resolve()


VALID_MODES = {"memo", "wiki", "personal", "book", "business",
               "github-codebase", "website"}


def test_set_updates_mode(tmp_path):
    db = _fresh_db(tmp_path)
    root = tmp_path / "v1"
    root.mkdir()
    registry.add_vault(db, name="v1", path=root,
                       type_="markdown", mode="wiki")
    vault_ops.set_(db, "v1", mode="memo")
    assert registry.get_vault_by_name(db, "v1")["mode"] == "memo"
    assert (root / "inbox").is_dir()


def test_set_invalid_mode_rejected(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError):
        vault_ops.set_(db, "v1", mode="nonsense")
    assert registry.get_vault_by_name(db, "v1")["mode"] == "wiki"


def test_set_mode_refuses_missing_vault_path(tmp_path):
    db = _fresh_db(tmp_path)
    root = tmp_path / "missing"
    registry.add_vault(db, name="v1", path=root, type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError, match="path is missing"):
        vault_ops.set_(db, "v1", mode="business")
    assert not root.exists()
    assert registry.get_vault_by_name(db, "v1")["mode"] == "wiki"


def test_set_merges_config_pairs(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    vault_ops.set_(db, "v1", config_pairs=["theme=dark", "limit=5"])
    cfg = _json.loads(registry.get_vault_by_name(db, "v1")["config_json"])
    assert cfg == {"theme": "dark", "limit": "5"}


def test_set_requires_at_least_one_field(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError):
        vault_ops.set_(db, "v1")


def test_archive_hides_from_default_list_and_clears_active(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    registry.set_active(db, "v1")
    vault_ops.archive(db, "v1")
    assert registry.get_active(db) is None
    assert {v["name"] for v in registry.list_vaults(db)} == set()
    assert {v["name"] for v in registry.list_vaults(db, include_archived=True)} == {"v1"}


def test_unarchive_restores_visibility(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    vault_ops.archive(db, "v1")
    vault_ops.unarchive(db, "v1")
    assert {v["name"] for v in registry.list_vaults(db)} == {"v1"}
    assert registry.get_vault_by_name(db, "v1")["archived_at"] is None


def test_archive_is_idempotent(tmp_path):
    db = _fresh_db(tmp_path)
    registry.add_vault(db, name="v1", path=tmp_path / "v1",
                       type_="markdown", mode="wiki")
    vault_ops.archive(db, "v1")
    vault_ops.archive(db, "v1")  # no raise
    assert registry.get_vault_by_name(db, "v1")["archived_at"] is not None


def test_delete_soft_moves_to_trash_and_forgets(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "home"))
    from scripts.paths import registry_path, omw_home
    db = registry_path()
    registry.init_db(db)
    src = tmp_path / "v1"
    src.mkdir()
    (src / "keep.md").write_text("data")
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    out = vault_ops.delete(db, "v1", hard=False, yes=False, now_ts="20260625-000000")
    assert registry.get_vault_by_name(db, "v1") is None
    assert not src.exists()
    trash = omw_home() / ".trash" / "20260625-000000-v1"
    assert (trash / "keep.md").read_text() == "data"
    assert out["trash"].endswith("20260625-000000-v1")


def test_delete_hard_without_yes_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "home"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    src = tmp_path / "v1"
    src.mkdir()
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError):
        vault_ops.delete(db, "v1", hard=True, yes=False, now_ts="x")
    # nothing removed, still registered
    assert src.exists()
    assert registry.get_vault_by_name(db, "v1") is not None


def test_delete_hard_with_yes_removes_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "home"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    src = tmp_path / "v1"
    src.mkdir()
    (src / "x.md").write_text("data")
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    vault_ops.delete(db, "v1", hard=True, yes=True, now_ts="x")
    assert not src.exists()
    assert registry.get_vault_by_name(db, "v1") is None


def test_update_mode_config_empty_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    with pytest.raises(registry.VaultError):
        registry.update_mode_config(db, "v1")


def test_cli_vault_rename(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="a", path=tmp_path / "a", type_="markdown", mode="wiki")
    ret = omw_cli.main(["vault", "rename", "a", "b"])
    assert ret == 0
    assert registry.get_vault_by_name(db, "b") is not None
    assert registry.get_vault_by_name(db, "a") is None


def test_cli_vault_move(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    src = tmp_path / "src_vault"
    src.mkdir()
    (src / ".oh-my-wiki").mkdir()
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    new_dst = tmp_path / "dst_vault"
    ret = omw_cli.main(["vault", "move", "v1", str(new_dst)])
    assert ret == 0
    row = registry.get_vault_by_name(db, "v1")
    assert row is not None
    assert Path(row["path"]).resolve() == new_dst.resolve()
    assert new_dst.exists()


def test_cli_vault_set(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "v1"
    root.mkdir()
    registry.add_vault(db, name="v1", path=root, type_="markdown", mode="wiki")
    ret = omw_cli.main(["vault", "set", "v1", "--mode", "memo"])
    assert ret == 0
    row = registry.get_vault_by_name(db, "v1")
    assert row["mode"] == "memo"


def test_cli_vault_archive_and_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="v1", path=tmp_path / "v1", type_="markdown", mode="wiki")
    ret = omw_cli.main(["vault", "archive", "v1"])
    assert ret == 0
    capsys.readouterr()
    omw_cli.main(["vault", "list"])
    out = capsys.readouterr().out
    data = _json.loads(out)
    names = [v["name"] for v in data]
    assert "v1" not in names
    capsys.readouterr()
    omw_cli.main(["vault", "list", "--all"])
    out2 = capsys.readouterr().out
    data2 = _json.loads(out2)
    names2 = [v["name"] for v in data2]
    assert "v1" in names2


def test_cli_vault_delete_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    src = tmp_path / "v1_folder"
    src.mkdir()
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    registry.add_vault(db, name="v1", path=src, type_="markdown", mode="wiki")
    ret = omw_cli.main(["vault", "delete", "v1"])
    assert ret == 0
    assert registry.get_vault_by_name(db, "v1") is None
    trash_dir = tmp_path / ".trash"
    assert trash_dir.exists()
    trashed = list(trash_dir.iterdir())
    assert len(trashed) >= 1
