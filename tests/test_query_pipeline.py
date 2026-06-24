from scripts import query_pipeline


def test_context_assembles_bodies_and_citations(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    long_body = "## Summary\n\n" + " ".join(f"forecast{i}" for i in range(50))
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/deepar.md": f"---\ntitle: DeepAR\ntype: concept\n---\n\n{long_body}\n",
    })
    out = query_pipeline.context(db, vault_id=vid, q="forecast1", limit=8)
    assert out["query"] == "forecast1"
    assert out["strategy"] in ("fts", "embedding", "hybrid", "llm")
    assert any(h["slug"] == "deepar" for h in out["hits"])
    hit = next(h for h in out["hits"] if h["slug"] == "deepar")
    assert "forecast1" in hit["body"]
    assert {"slug": "deepar", "title": "DeepAR",
            "relpath": "wiki/concepts/deepar.md"} in out["citations"]


def test_context_caps_body(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    big = "## Summary\n\n" + ("word " * 3000)  # > 4000 chars
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/big.md": f"---\ntitle: Big\ntype: concept\n---\n\n{big}\n",
    })
    out = query_pipeline.context(db, vault_id=vid, q="word", limit=8, body_cap=4000)
    hit = next(h for h in out["hits"] if h["slug"] == "big")
    assert len(hit["body"]) <= 4000 and hit["truncated"] is True
