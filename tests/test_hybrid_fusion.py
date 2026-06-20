from scripts.search_index import rrf_fuse, search_strategy
import scripts.search_index as search_index


def test_rrf_merges_and_ranks():
    """Items appearing in multiple lists score higher via RRF."""
    r1 = ["a", "b", "c"]
    r2 = ["c", "a", "d"]
    result = rrf_fuse([r1, r2])
    ranked = [item for item, _ in result]
    # 'a' and 'c' appear in both lists → should outrank 'b' and 'd'
    assert ranked.index("a") < ranked.index("b")
    assert ranked.index("a") < ranked.index("d")
    assert ranked.index("c") < ranked.index("b")
    assert ranked.index("c") < ranked.index("d")
    assert ranked[0] in {"a", "c"}


def test_search_strategy_fts_matches_query():
    """strategy='fts' delegates to the existing query() function."""
    fake_hit = {"relpath": "wiki/foo.md", "title": "Foo", "score": 1.0}

    original_query = search_index.query

    def mock_query(db_path, *, vault_id, query, limit, visibility=None):
        return [fake_hit]

    search_index.query = mock_query
    try:
        result = search_strategy(None, vault_id=1, q="q", limit=3, strategy="fts")
        assert result == [fake_hit]
    finally:
        search_index.query = original_query


def test_search_strategy_uses_fts_query_for_lexical_leg(monkeypatch):
    seen = {}
    def fake_query(db, *, vault_id, query, limit, visibility=None):
        seen["q"] = query
        return [{"relpath": "wiki/x.md", "score": 1.0}]
    monkeypatch.setattr(search_index, "query", fake_query)
    search_index.search_strategy(None, vault_id=1, q="ARIMA와", limit=3,
                                 strategy="fts", fts_query="ARIMA")
    assert seen["q"] == "ARIMA"   # the normalized fts_query reached the FTS leg
