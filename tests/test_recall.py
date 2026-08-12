"""Unit tests for scripts.recall — render_always_on_block + marker-agnostic upsert."""
from scripts import recall, text_normalize


def test_always_on_block_is_wiki_first_and_marked():
    block = recall.render_always_on_block()
    assert "omw-wiki-first:start" in block and "omw-wiki-first:end" in block
    assert "omw find" in block and "raw/" in block


def test_static_hook_guidance_is_english():
    """OMW-authored hook instructions stay English; user page titles may use any language."""
    outputs = [
        recall.render_capture_cue(),
        recall.render_llm_guidance("route"),
        recall.render_llm_guidance("generative"),
        recall.render_recall_block("auto"),
        recall.render_always_on_block(),
    ]
    assert all(not any("가" <= char <= "힣" for char in output) for output in outputs)


def test_concrete_recall_hook_guidance_is_english(monkeypatch):
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: [
        {"title": "Forecasting", "relpath": "wiki/forecasting.md", "tags": [], "score": 2.0}
    ])
    monkeypatch.setattr(recall, "_record_use", lambda *a, **k: None)
    cfg = {"mode": "auto", "strategy": "fts", "top_k": 3, "min_score": 1.0}
    output = recall._recall_body(cfg, "forecasting")
    assert not any("가" <= char <= "힣" for char in output)


def test_normalize_query_delegates_and_preserves_behavior():
    assert recall.normalize_query("학교에서 ARIMA와") == "학교 ARIMA"
    assert recall.normalize_query("학교에서") == text_normalize.normalize_text("학교에서")


def test_strip_josa_still_callable():
    assert recall._strip_josa("평가지표를") == "평가지표"


def test_hybrid_recall_uses_quality_gate(tmp_path, monkeypatch):
    """Only hook-side hybrid recall opts into strict relevance filtering."""
    from scripts import config, embed, search_index
    from scripts import paths

    db = tmp_path / "registry.db"
    db.touch()
    monkeypatch.setattr(paths, "registry_path", lambda: db)
    monkeypatch.setattr(config, "load_config", lambda: {
        "recall": {"strategy": "hybrid", "embedding": {"provider": "fake"}}
    })
    monkeypatch.setattr(recall, "_active", lambda _db: {"id": 7})
    monkeypatch.setattr(embed, "get_embedder", lambda cfg: object())
    seen = {}

    def fake_search(*args, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(search_index, "search_strategy", fake_search)
    assert recall._hits("ZimaBoard NIC 협상", 3) == []
    assert seen["quality_gate"] is True
    assert seen["limit"] == 3


def test_embedding_recall_also_uses_quality_gate(tmp_path, monkeypatch):
    from scripts import config, embed, search_index
    from scripts import paths

    db = tmp_path / "registry.db"
    db.touch()
    monkeypatch.setattr(paths, "registry_path", lambda: db)
    monkeypatch.setattr(config, "load_config", lambda: {
        "recall": {"strategy": "embedding", "embedding": {"provider": "fake"}}
    })
    monkeypatch.setattr(recall, "_active", lambda _db: {"id": 7})
    monkeypatch.setattr(embed, "get_embedder", lambda cfg: object())
    seen = {}
    monkeypatch.setattr(
        search_index, "search_strategy",
        lambda *args, **kwargs: seen.update(kwargs) or [],
    )
    recall._hits("프로젝트 의미 검색 질문", 3)
    assert seen["quality_gate"] is True
