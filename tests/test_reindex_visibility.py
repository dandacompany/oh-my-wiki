# tests/test_reindex_visibility.py
from scripts import registry, reindex


def _make_vault(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    return db, root, vid


def _visibility(db, relpath):
    conn = registry.connect(db)
    try:
        return conn.execute("SELECT visibility FROM notes WHERE relpath=?", (relpath,)
                           ).fetchone()["visibility"]
    finally:
        conn.close()


def test_reindex_reads_public_visibility(tmp_path):
    db, root, vid = _make_vault(tmp_path)
    (root / "wiki" / "pub.md").write_text(
        "---\ntitle: Pub\ndate: 2026-06-02\ntype: note\ntags: []\nvisibility: public\n---\n\nbody\n")
    (root / "wiki" / "priv.md").write_text(
        "---\ntitle: Priv\ndate: 2026-06-02\ntype: note\ntags: []\n---\n\nbody\n")
    reindex.full(db, vault_id=vid)
    assert _visibility(db, "wiki/pub.md") == "public"
    assert _visibility(db, "wiki/priv.md") == "private"  # unset → private
