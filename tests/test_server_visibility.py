# tests/test_server_visibility.py
from scripts import registry, reindex, server


def _vault(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    registry.set_active(db, "v")
    (root / "wiki" / "pub.md").write_text(
        "---\ntitle: fox public\ndate: 2026-06-02\ntype: note\ntags: []\nvisibility: public\n---\n\nfox\n")
    (root / "wiki" / "priv.md").write_text(
        "---\ntitle: fox private\ndate: 2026-06-02\ntype: note\ntags: []\n---\n\nfox\n")
    vid = registry.list_vaults(db)[0]["id"]
    reindex.full(db, vault_id=vid)
    return db


def test_handle_query_serves_public_only(tmp_path):
    db = _vault(tmp_path)
    result = server.handle_query({"text": "fox", "limit": 10}, db_path=db)
    relpaths = {h["relpath"] for h in result["hits"]}
    assert relpaths == {"wiki/pub.md"}  # private page is never served
    assert result["count"] == 1
