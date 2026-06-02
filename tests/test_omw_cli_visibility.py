# tests/test_omw_cli_visibility.py
import json

from scripts import omw_cli, registry, reindex
from scripts.paths import ensure_home, registry_path


def _seed(tmp_path):
    ensure_home()
    db = registry_path()
    root = tmp_path / "v"
    (root / "wiki").mkdir(parents=True)
    registry.init_db(db)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    registry.set_active(db, "v")
    (root / "wiki" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-06-02\ntype: note\ntags: []\n---\n\nbody\n")
    vid = registry.list_vaults(db)[0]["id"]
    reindex.full(db, vault_id=vid)
    return db, root


def test_visibility_get_defaults_private(tmp_path, capsys):
    _seed(tmp_path)
    assert omw_cli.main(["visibility", "get", "wiki/a.md"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["relpath"] == "wiki/a.md"
    assert out["visibility"] == "private"


def test_visibility_set_public_updates_file_and_index(tmp_path, capsys):
    db, root = _seed(tmp_path)
    assert omw_cli.main(["visibility", "set", "wiki/a.md", "public"]) == 0
    assert "visibility: public" in (root / "wiki" / "a.md").read_text()
    from scripts import search_index
    vid = registry.list_vaults(db)[0]["id"]
    hits = search_index.query(db, vault_id=vid, query="A", limit=5, visibility="public")
    assert {h["relpath"] for h in hits} == {"wiki/a.md"}


def test_visibility_set_multiple_relpaths(tmp_path):
    db, root = _seed(tmp_path)
    (root / "wiki" / "b.md").write_text(
        "---\ntitle: B\ndate: 2026-06-02\ntype: note\ntags: []\n---\n\nbody\n")
    vid = registry.list_vaults(db)[0]["id"]
    reindex.full(db, vault_id=vid)
    assert omw_cli.main(["visibility", "set", "wiki/a.md", "wiki/b.md", "public"]) == 0
    assert "visibility: public" in (root / "wiki" / "a.md").read_text()
    assert "visibility: public" in (root / "wiki" / "b.md").read_text()


def test_visibility_set_reports_missing_and_exits_nonzero(tmp_path, capsys):
    db, root = _seed(tmp_path)
    rc = omw_cli.main(["visibility", "set", "wiki/a.md", "wiki/ghost.md", "public"])
    out = json.loads(capsys.readouterr().out)
    assert out["updated"] == ["wiki/a.md"]
    assert out["missing"] == ["wiki/ghost.md"]
    assert rc == 1  # any missing → nonzero
    assert "visibility: public" in (root / "wiki" / "a.md").read_text()
