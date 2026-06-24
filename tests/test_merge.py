import json

from scripts import registry, reindex


def test_reindex_persists_aliases(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/winner.md": (
            "---\ntitle: Winner\ntype: concept\ntags: [t]\n"
            "aliases: [old-name, other-alias]\n---\n\n## Summary\n\nbody\n"
        ),
    })
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        row = conn.execute(
            "SELECT aliases FROM notes WHERE vault_id = ? AND relpath = ?",
            (vid, "wiki/concepts/winner.md"),
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(row["aliases"]) == ["old-name", "other-alias"]
