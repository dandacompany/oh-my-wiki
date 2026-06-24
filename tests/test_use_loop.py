"""E1: omw serve must honour the configured retrieval strategy (not always FTS).

The spy asserts that handle_query delegates to search_index.search_strategy
with visibility="public", which is the contract this task introduces.
"""
from tests.conftest import make_vault_with_pages
from scripts import server, search_index


def test_serve_uses_search_strategy(monkeypatch, tmp_path):
    db, vid = make_vault_with_pages(
        tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nwidgets"}
    )
    called = {}

    def spy(db_path, *, vault_id, q, limit, strategy, embedder=None,
            visibility=None, fts_query=None):
        called.update(strategy=strategy, visibility=visibility)
        return []

    monkeypatch.setattr(search_index, "search_strategy", spy)
    # handle_query real signature: (payload: dict, *, db_path, default_vault, max_limit)
    server.handle_query(
        {"text": "widgets", "vault": "default"},
        db_path=db,
        max_limit=5,
    )
    assert "strategy" in called, "search_strategy was never called"
    assert called["visibility"] == "public"
