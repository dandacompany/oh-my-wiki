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


def test_fts_recall_gates_hits_that_name_nothing(tmp_path, monkeypatch):
    """The fts arm had no precision filter, so it injected its top hits on every
    prompt regardless of what the prompt was about."""
    from scripts import config, search_index
    from scripts import paths

    db = tmp_path / "registry.db"
    db.touch()
    monkeypatch.setattr(paths, "registry_path", lambda: db)
    monkeypatch.setattr(config, "load_config", lambda: {"recall": {"strategy": "fts"}})
    monkeypatch.setattr(recall, "_active", lambda _db: {"id": 7})
    monkeypatch.setattr(search_index, "query", lambda *a, **k: [
        {"relpath": "raw/import/hermes-top-10-skills.md", "title": "Hermes skills"},
        {"relpath": "wiki/concepts/에이전트-메모리.md", "title": "에이전트 메모리"},
    ])
    hits = recall._hits("에이전트 메모리 3층 구조가 뭐였지", 3)
    assert [h["relpath"] for h in hits] == ["wiki/concepts/에이전트-메모리.md"]


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


def test_strategy_thresholds_use_each_score_scale(monkeypatch):
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: [
        {"title": "Semantic", "relpath": "wiki/semantic.md", "tags": [], "score": 0.52}
    ])
    monkeypatch.setattr(recall, "_record_use", lambda *a, **k: None)
    cfg = {"mode": "auto", "strategy": "embedding", "top_k": 3,
           "min_score": 9.0}
    assert "semantic.md" in recall._recall_body(cfg, "semantic retrieval question")


def test_strategy_threshold_override_and_unreachable_diagnostic():
    cfg = {"min_score": 2.0, "min_scores": {"embedding": 1.2, "hybrid": 0.5}}
    assert recall.score_threshold(cfg, "fts") == 2.0
    assert recall.score_threshold(cfg, "hybrid") == 0.5
    assert "unreachable" in recall.threshold_diagnostics(cfg)[0]


def test_recall_threshold_overrides_do_not_mutate_later_defaults(monkeypatch):
    configs = [
        {"recall": {"min_scores": {"embedding": 0.91}}},
        {"recall": {}},
    ]
    monkeypatch.setattr("scripts.config.load_config", lambda: configs.pop(0))

    assert recall._cfg()["min_scores"]["embedding"] == 0.91
    assert recall._cfg()["min_scores"]["embedding"] == 0.34


def test_preamble_includes_same_project_staged_session(monkeypatch):
    monkeypatch.setattr(recall, "_base_preamble", lambda: "<omw-wiki>active</omw-wiki>")
    monkeypatch.setattr(recall, "_session_context", lambda payload: "<omw-session>resume</omw-session>")

    out = recall.preamble({"cwd": "/project", "session_id": "new"})

    assert "<omw-wiki>active" in out
    assert "<omw-session>resume" in out


def test_resume_prompt_includes_session_context_but_ordinary_prompt_does_not(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: {
        "mode": "auto", "strategy": "fts", "top_k": 3, "min_score": 1.0,
        "capture": False,
    })
    monkeypatch.setattr(recall, "_recall_body", lambda cfg, text: "")
    monkeypatch.setattr(recall, "_session_context", lambda payload: "<omw-session>unfinished</omw-session>")

    resumed = recall.prompt(None, payload={"prompt": "지난 작업 어디까지 했는지 이어서 진행해", "cwd": "/p"})
    ordinary = recall.prompt(None, payload={"prompt": "새로운 정렬 알고리즘을 설명해줘", "cwd": "/p"})

    assert "unfinished" in resumed
    assert ordinary == ""


def test_pretool_injects_high_confidence_file_context(monkeypatch):
    monkeypatch.setattr(recall, "_has_active_vault", lambda: True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [
        {"title": "Recall hooks", "relpath": "wiki/recall-hooks.md", "score": 7.2},
    ])
    payload = {"tool_name": "Read", "tool_input": {"file_path": "scripts/recall.py"}}

    out = recall.pretool(payload)

    assert "Recall hooks" in out and "wiki/recall-hooks.md" in out
    assert "primary source" not in out


def test_pretool_combines_raw_nudge_and_related_file_context(monkeypatch):
    monkeypatch.setattr(recall, "_has_active_vault", lambda: True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [
        {"title": "Raw source policy", "relpath": "wiki/raw-policy.md", "score": 8.0},
    ])
    payload = {"tool_name": "Read", "tool_input": {"file_path": "raw/source.md"}}

    out = recall.pretool(payload)

    assert "Before reading `raw/`" in out
    assert "Raw source policy" in out


def test_pretool_stays_silent_for_unrelated_file(monkeypatch):
    monkeypatch.setattr(recall, "_has_active_vault", lambda: True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [])
    payload = {"tool_name": "Read", "tool_input": {"file_path": "src/unrelated.py"}}
    assert recall.pretool(payload) == ""


def test_error_and_file_signals_run_one_focused_followup_search(monkeypatch):
    calls = []
    monkeypatch.setattr(recall, "_hits", lambda query, top_k: calls.append(query) or [])
    cfg = {"mode": "auto", "strategy": "fts", "top_k": 3, "min_score": 1.0}

    recall._recall_body(cfg, "auth/session.py failed with ConnectionError")

    assert calls[0] == "auth/session.py failed with ConnectionError"
    assert len(calls) == 2
    assert "ConnectionError" in calls[1] and "auth" in calls[1] and "session" in calls[1]


def test_signal_followup_never_exceeds_configured_top_k(monkeypatch):
    primary = [
        {"relpath": f"wiki/p{i}.md", "title": f"P{i}", "score": 10 - i}
        for i in range(3)
    ]
    followup = [
        {"relpath": f"wiki/f{i}.md", "title": f"F{i}", "score": 20 - i}
        for i in range(3)
    ]
    monkeypatch.setattr(
        recall, "_hits", lambda query, top_k: followup if query == "ConnectionError" else primary)
    monkeypatch.setattr(recall, "_signal_queries", lambda text: ["ConnectionError"])
    monkeypatch.setattr(recall, "_record_use", lambda relpaths: None)
    cfg = {"mode": "auto", "strategy": "fts", "top_k": 3, "min_score": 1.0}

    out = recall._recall_body(cfg, "failed with ConnectionError")

    assert out.count("\n- ") == 3


def test_standalone_recall_main_delegates_to_top_level_cli(monkeypatch):
    seen = {}

    def fake_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr("scripts.omw_cli.main", fake_main)

    assert recall.main(["capture", "--host", "codex"]) == 0
    assert seen["argv"] == ["recall", "capture", "--host", "codex"]
