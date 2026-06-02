# tests/test_search_index_visibility.py
from scripts import registry, reindex, search_index


def _vault_with_pages(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    (root / "wiki" / "pub.md").write_text(
        "---\ntitle: Karpathy fox\ndate: 2026-06-02\ntype: note\ntags: []\nvisibility: public\n---\n\nfox\n")
    (root / "wiki" / "priv.md").write_text(
        "---\ntitle: Karpathy fox\ndate: 2026-06-02\ntype: note\ntags: []\n---\n\nfox\n")
    reindex.full(db, vault_id=vid)
    return db, vid


def test_query_no_filter_returns_all(tmp_path):
    db, vid = _vault_with_pages(tmp_path)
    hits = search_index.query(db, vault_id=vid, query="fox", limit=10)
    assert {h["relpath"] for h in hits} == {"wiki/pub.md", "wiki/priv.md"}


def test_query_public_only(tmp_path):
    db, vid = _vault_with_pages(tmp_path)
    hits = search_index.query(db, vault_id=vid, query="fox", limit=10, visibility="public")
    assert {h["relpath"] for h in hits} == {"wiki/pub.md"}


def test_query_public_only_fallback_path(tmp_path, monkeypatch):
    # Force the non-FTS token-scorer fallback and verify it also filters.
    db, vid = _vault_with_pages(tmp_path)
    monkeypatch.setattr("scripts.search_index.fts.fts5_available", lambda: False)
    hits = search_index.query(db, vault_id=vid, query="fox", limit=10, visibility="public")
    assert {h["relpath"] for h in hits} == {"wiki/pub.md"}
