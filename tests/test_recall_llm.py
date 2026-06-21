# tests/test_recall_llm.py
from scripts import recall


def test_llm_is_implemented_no_fallback():
    assert recall.effective_strategy("llm") == "llm"


def test_render_llm_guidance_route_and_generative():
    r = recall.render_llm_guidance("route")
    g = recall.render_llm_guidance("generative")
    assert recall.MARKER in r and recall.MARKER in g
    # route is about choosing how to search; generative is about reading+filtering
    assert "omw find" in r and ("키워드" in r or "의미" in r)
    assert "omw find" in g and ("읽" in g)              # read the candidates
    # unknown submode falls back to route text
    assert recall.render_llm_guidance("nonsense") == r


def test_prompt_llm_route_emits_guidance_without_search(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: {
        "mode": "advisory", "strategy": "llm", "llm_submode": "route",
        "min_score": 1.0, "top_k": 3, "snippet_chars": 280})
    def _boom(*a, **k):
        raise AssertionError("_hits must not be called on the llm path")
    monkeypatch.setattr(recall, "_hits", _boom)
    out = recall.prompt("ARIMA와 Prophet의 차이를 설명해줘")
    assert out == recall.render_llm_guidance("route")


def test_prompt_llm_generative_emits_generative_guidance(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: {
        "mode": "auto", "strategy": "llm", "llm_submode": "generative",
        "min_score": 1.0, "top_k": 3, "snippet_chars": 280})
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("no search on llm path")))
    out = recall.prompt("수요예측 모델 선택 기준이 뭐야")
    assert out == recall.render_llm_guidance("generative")


def test_prompt_llm_off_and_trivial_short_circuit(monkeypatch):
    base = {"strategy": "llm", "llm_submode": "route",
            "min_score": 1.0, "top_k": 3, "snippet_chars": 280}
    monkeypatch.setattr(recall, "_cfg", lambda: {**base, "mode": "off"})
    assert recall.prompt("ARIMA와 Prophet 차이 설명해줘") == ""
    monkeypatch.setattr(recall, "_cfg", lambda: {**base, "mode": "advisory"})
    assert recall.prompt("ok") == ""          # trivial gate wins over llm


def test_cost_warning_reworded_still_flags_auto_llm():
    assert recall.cost_warning("auto", "llm") is not None
    assert recall.cost_warning("advisory", "llm") is None
    assert recall.cost_warning("auto", "fts") is None


def test_hits_never_searches_under_llm(monkeypatch):
    """Regression: _hits must return [] immediately when strategy=llm, without
    touching search_index, vector_index, or creating any embedder."""

    # Make _cfg return llm strategy (patches the config loading path used by _hits)
    import types
    import scripts.recall as _recall_mod

    # Patch config.load_config to return recall.strategy=llm
    fake_config = types.ModuleType("config")
    fake_config.load_config = lambda: {"recall": {"strategy": "llm"}}
    monkeypatch.setattr(_recall_mod, "_cfg", lambda: {
        "mode": "auto", "strategy": "llm", "llm_submode": "route",
        "min_score": 1.0, "top_k": 3, "snippet_chars": 280,
    })

    # Patch scripts.config inside the module so _hits sees llm strategy
    import scripts.config as real_config
    original_load = real_config.load_config
    monkeypatch.setattr(real_config, "load_config",
                        lambda: {"recall": {"strategy": "llm"}})

    # Make search_index.query and search_index.search_strategy raise if called
    import scripts.search_index as si
    monkeypatch.setattr(si, "query",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("search_index.query must not be called for llm strategy")))
    monkeypatch.setattr(si, "search_strategy",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("search_index.search_strategy must not be called for llm strategy")))

    # Also guard vector_index if it exists
    try:
        import scripts.vector_index as vi
        monkeypatch.setattr(vi, "query",
                            lambda *a, **k: (_ for _ in ()).throw(
                                AssertionError("vector_index.query must not be called for llm strategy")))
    except (ImportError, AttributeError):
        pass

    result = recall._hits("some query about the project", 3)
    assert result == [], f"expected [] but got {result!r}"
