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


def test_hydrate_fails_closed_under_public_on_db_error(tmp_path, monkeypatch):
    """Regression: when DB raises under visibility='public', untitled vector hits are
    DROPPED (fail-closed). Under visibility=None both hits are returned (fail-open preserved)."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "f.md").write_text(
        "---\ntitle: F\ndate: 2026-01-01\ntype: concept\ntags: []\n---\nbody\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)

    # Force every registry.connect call to raise, simulating a DB failure.
    monkeypatch.setattr(search_index.registry, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    vector_hit = {"relpath": "wiki/concepts/v.md", "score": 0.9}          # no title
    fts_hit    = {"relpath": "wiki/concepts/f.md", "title": "F",
                  "summary": "s", "tags": [], "score": 1.0}               # has title

    # --- visibility='public': fail CLOSED → only fts hit survives ---
    out_public = search_index.hydrate(db, vault_id=vid,
                                      hits=[vector_hit, fts_hit],
                                      visibility="public")
    relpaths_public = {h["relpath"] for h in out_public}
    assert "wiki/concepts/v.md" not in relpaths_public, \
        "untitled vector hit must be DROPPED when DB raises under visibility='public'"
    assert "wiki/concepts/f.md" in relpaths_public, \
        "already-titled fts hit must be KEPT"

    # --- visibility=None: fail OPEN → both hits returned unchanged ---
    out_none = search_index.hydrate(db, vault_id=vid,
                                    hits=[dict(vector_hit), dict(fts_hit)],
                                    visibility=None)
    relpaths_none = {h["relpath"] for h in out_none}
    assert "wiki/concepts/v.md" in relpaths_none, \
        "vector hit must be KEPT when visibility=None (hot-path best-effort)"
    assert "wiki/concepts/f.md" in relpaths_none


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


def test_tokens_strip_josa_for_symmetric_match():
    # body-side josa form and bare-noun query reduce to the same token
    assert "학교" in search_index._tokens("학교에서 배웠다")
    assert search_index._tokens("학교") == ["학교"]


def test_tokens_lowercase_ascii_preserved():
    assert search_index._tokens("ARIMA Model") == ["arima", "model"]


def test_tokens_split_multiword_normalizer_output(monkeypatch):
    from scripts import text_normalize

    monkeypatch.setattr(text_normalize, "normalize_text", lambda text: "링크 되다 NIC")
    assert search_index._tokens("ignored") == ["링크", "되다", "nic"]


def test_quality_gate_checks_bounded_body_across_distant_matches(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    raw = root / "raw"
    raw.mkdir()
    gap = " ".join(["채움"] * 120)
    (raw / "hostinger.md").write_text(
        "도커 " + gap + " 컨테이너 " + gap + " 에이전트 " + gap
        + " 홈 경로 " + gap + " 예상과 다르게 잡힌 원인",
        encoding="utf-8",
    )
    (root / "wiki" / "concepts" / "noise.md").write_text(
        "---\ntitle: 일반 에이전트 문서\ndate: 2026-01-01\ntype: concept\ntags: []\n---\n"
        "에이전트 일반 설명",
        encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)

    out = search_index.search_strategy(
        db, vault_id=vid,
        q="도커 컨테이너에서 에이전트 홈 경로가 예상과 다르게 잡힌 문제",
        limit=3, strategy="hybrid", embedder=None, quality_gate=True,
    )
    assert out and out[0]["relpath"] == "raw/hostinger.md"


# --- shared name gate -------------------------------------------------------
# One rule, one home. recall's pretool hook and the fts recall path both need
# "is this hit actually about the query", and two copies would drift.

def test_names_query_keeps_a_hit_that_names_a_term():
    hits = [{"relpath": "wiki/concepts/hybrid-search.md", "title": "Hybrid search"}]
    assert search_index.names_query(hits, "hybrid-search") == hits


def test_names_query_drops_a_hit_that_names_nothing():
    hits = [{"relpath": "raw/2026-07-08-hermes-plugins.md", "title": "Hermes plugins"}]
    assert search_index.names_query(hits, "key-rotation") == []


def test_names_query_matches_a_spaced_title_for_a_hyphenated_term():
    hits = [{"relpath": "wiki/concepts/n1.md", "title": "Key rotation"}]
    assert len(search_index.names_query(hits, "key-rotation")) == 1


def test_names_query_requires_word_boundaries_for_latin_terms():
    hits = [{"relpath": "wiki/concepts/sandbox.md", "title": "Sandbox"}]
    assert search_index.names_query(hits, "box") == []


def test_names_query_accepts_two_syllable_hangul():
    hits = [{"relpath": "wiki/concepts/번들-구성.md", "title": ""}]
    assert len(search_index.names_query(hits, "번들")) == 1


def test_a_date_shaped_term_cannot_qualify_a_hit_on_its_own():
    """Dates name a filename convention, not a subject — only 'kiwi' may match."""
    hits = [{"relpath": "raw/2026-07-08-anything.md", "title": ""},
            {"relpath": "wiki/concepts/kiwi.md", "title": "Kiwi"}]
    assert [h["relpath"] for h in search_index.names_query(hits, "2026-07-08 kiwi")] == [
        "wiki/concepts/kiwi.md"]


def test_names_query_returns_everything_when_no_term_can_qualify():
    """A query with nothing specific enough must not silently drop every hit."""
    hits = [{"relpath": "wiki/concepts/x.md", "title": "X"}]
    assert search_index.names_query(hits, "db") == hits


def test_a_hangul_term_matches_through_its_josa():
    """Prompts carry postpositions ('번들을'); the page title does not. Dropping
    the hit would make Korean prompt recall go silent."""
    hits = [{"relpath": "wiki/summaries/persona.md", "title": "페르소나 번들"}]
    assert len(search_index.names_query(hits, "번들을 실행")) == 1


def test_name_terms_is_public_for_callers_that_pre_check():
    assert search_index.name_terms("key-rotation") == [["key", "rotation"]]
    assert search_index.name_terms("db 2026-07-08") == []


def test_on_vague_drop_returns_nothing_when_no_term_qualifies():
    hits = [{"relpath": "wiki/concepts/x.md", "title": "X"}]
    assert search_index.names_query(hits, "db", on_vague="drop") == []
    assert search_index.names_query(hits, "db", on_vague="keep") == hits
