from scripts import registry, reindex


def test_reindex_persists_type_and_status(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/c.md": "---\ntitle: C\ntype: concept\nstatus: processed\n---\n\n## Summary\n\nx\n",
        "wiki/concepts/n.md": "---\ntitle: N\n---\n\n## Summary\n\ny\n",
    })
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        c = conn.execute("SELECT type, status FROM notes WHERE relpath = ?",
                         ("wiki/concepts/c.md",)).fetchone()
        n = conn.execute("SELECT type, status FROM notes WHERE relpath = ?",
                         ("wiki/concepts/n.md",)).fetchone()
    finally:
        conn.close()
    assert c["type"] == "concept" and c["status"] == "processed"
    assert n["type"] is None and n["status"] is None
