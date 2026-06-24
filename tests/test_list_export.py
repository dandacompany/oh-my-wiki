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


def test_list_faceted(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\nstatus: processed\ntags: [ml]\n---\n\n## Summary\n\na\n",
        "wiki/entities/b.md": "---\ntitle: B\ntype: entity\nstatus: superseded\ntags: [ml, x]\n---\n\n## Summary\n\nb\n",
    })
    def rels(rows):
        return {r["relpath"] for r in rows}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, type_="concept")) == {"wiki/concepts/a.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, status="superseded")) == {"wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="ml")) == {"wiki/concepts/a.md", "wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="x")) == {"wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="ml", type_="entity")) == {"wiki/entities/b.md"}
