from scripts import fts, registry, reindex
from scripts import search_index


def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "v"
    (root / "wiki" / "concepts").mkdir(parents=True)
    v = registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    return db, root, v["id"]


def test_query_finds_body_only_term_via_fts(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "a.md").write_text(
        "---\ntitle: Alpha\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nthe quick brown fox\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)
    hits = search_index.query(db, vault_id=vid, query="fox", limit=5)  # body-only term
    assert any(h["relpath"] == "wiki/concepts/a.md" for h in hits)


def test_query_falls_back_without_fts5(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "a.md").write_text(
        "---\ntitle: Alpha Fox\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nbody\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)
    monkeypatch.setattr(fts, "fts5_available", lambda: False)
    hits = search_index.query(db, vault_id=vid, query="fox", limit=5)  # token path
    assert any(h["relpath"] == "wiki/concepts/a.md" for h in hits)
    assert set(hits[0]) >= {"relpath", "title", "summary", "tags", "score"}


def test_hydrate_fills_vector_hits(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "a.md").write_text(
        "---\ntitle: Alpha\ndate: 2026-01-01\ntype: concept\ntags: [x, y]\nsummary: body alpha\n---\nbody alpha\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)
    # a bare vector hit (only relpath/score) gets enriched
    hits = search_index.hydrate(db, vault_id=vid,
                                hits=[{"relpath": "wiki/concepts/a.md", "score": 0.9}])
    h = hits[0]
    assert h["title"] == "Alpha" and "alpha" in (h["summary"] or "").lower()
    assert set(h["tags"]) == {"x", "y"} and h["score"] == 0.9
    # an fts-style hit that already has title is left unchanged (no clobber)
    pre = {"relpath": "wiki/concepts/a.md", "title": "KEEP", "summary": "s",
           "tags": ["z"], "score": 1.0}
    out = search_index.hydrate(db, vault_id=vid, hits=[dict(pre)])
    assert out[0] == pre
    # an unknown relpath stays bare (no title key added)
    unk = search_index.hydrate(db, vault_id=vid,
                               hits=[{"relpath": "wiki/concepts/missing.md", "score": 0.5}])
    assert "title" not in unk[0]


def test_hydrate_empty_and_no_need_are_noops(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    assert search_index.hydrate(db, vault_id=vid, hits=[]) == []
    only_titled = [{"relpath": "x", "title": "T", "summary": "", "tags": [], "score": 1.0}]
    assert search_index.hydrate(db, vault_id=vid, hits=[dict(only_titled[0])]) == only_titled


def test_search_strategy_embedding_is_hydrated(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "a.md").write_text(
        "---\ntitle: Alpha\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nbody\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)

    class _FakeEmb:
        dim = 8
        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])  # no fts hits
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query",
                        lambda *a, **k: [{"relpath": "wiki/concepts/a.md", "score": 0.8}])
    out = search_index.search_strategy(db, vault_id=vid, q="alpha", limit=3,
                                       strategy="embedding", embedder=_FakeEmb())
    assert out and out[0]["relpath"] == "wiki/concepts/a.md"
    assert out[0]["title"] == "Alpha"        # hydrated


def test_search_strategy_hybrid_is_hydrated(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "a.md").write_text(
        "---\ntitle: Alpha\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nbody\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)

    class _FakeEmb:
        dim = 8
        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])  # fts empty
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query",
                        lambda *a, **k: [{"relpath": "wiki/concepts/a.md", "score": 0.8}])
    out = search_index.search_strategy(db, vault_id=vid, q="alpha", limit=3,
                                       strategy="hybrid", embedder=_FakeEmb())
    a = next(h for h in out if h["relpath"] == "wiki/concepts/a.md")
    assert a["title"] == "Alpha"             # embedding-only hit hydrated in the fused result


def test_search_strategy_embedding_respects_public_visibility(tmp_path, monkeypatch):
    """Regression: vector hits for PRIVATE notes must be dropped under visibility='public'."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    # public note
    (root / "wiki" / "concepts" / "pub.md").write_text(
        "---\ntitle: Public Page\ndate: 2026-01-01\ntype: concept\n"
        "tags: []\nvisibility: public\n---\npublic body\n",
        encoding="utf-8")
    # private note (no visibility key → defaults to private)
    (root / "wiki" / "concepts" / "priv.md").write_text(
        "---\ntitle: Private Page\ndate: 2026-01-01\ntype: concept\n"
        "tags: []\nvisibility: private\n---\nprivate body\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)

    class _FakeEmb:
        dim = 8
        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    # FTS leg returns nothing so only the vector leg contributes.
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    import scripts.vector_index as vector_index
    # Vector index returns BOTH notes as bare hits (simulating a privacy-unaware ANN search).
    monkeypatch.setattr(vector_index, "query",
                        lambda *a, **k: [
                            {"relpath": "wiki/concepts/pub.md", "score": 0.9},
                            {"relpath": "wiki/concepts/priv.md", "score": 0.85},
                        ])

    out = search_index.search_strategy(db, vault_id=vid, q="page", limit=5,
                                       strategy="embedding", embedder=_FakeEmb(),
                                       visibility="public")
    relpaths = {h["relpath"] for h in out}
    assert "wiki/concepts/pub.md" in relpaths, "public note must appear"
    assert "wiki/concepts/priv.md" not in relpaths, "private note must be dropped"


def test_search_strategy_embedding_no_visibility_returns_both(tmp_path, monkeypatch):
    """No-regression: without a visibility filter, both public and private notes appear."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "pub.md").write_text(
        "---\ntitle: Public Page\ndate: 2026-01-01\ntype: concept\n"
        "tags: []\nvisibility: public\n---\npublic body\n",
        encoding="utf-8")
    (root / "wiki" / "concepts" / "priv.md").write_text(
        "---\ntitle: Private Page\ndate: 2026-01-01\ntype: concept\n"
        "tags: []\nvisibility: private\n---\nprivate body\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)

    class _FakeEmb:
        dim = 8
        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    monkeypatch.setattr(search_index, "query", lambda *a, **k: [])
    import scripts.vector_index as vector_index
    monkeypatch.setattr(vector_index, "query",
                        lambda *a, **k: [
                            {"relpath": "wiki/concepts/pub.md", "score": 0.9},
                            {"relpath": "wiki/concepts/priv.md", "score": 0.85},
                        ])

    out = search_index.search_strategy(db, vault_id=vid, q="page", limit=5,
                                       strategy="embedding", embedder=_FakeEmb(),
                                       visibility=None)
    relpaths = {h["relpath"] for h in out}
    assert "wiki/concepts/pub.md" in relpaths, "public note must appear"
    assert "wiki/concepts/priv.md" in relpaths, "private note must also appear (no filter)"
