import json
from datetime import datetime, timedelta, timezone

from scripts import config, knowledge_candidates, registry, session_capture


def _db(tmp_path, monkeypatch):
    home = tmp_path / ".omw"
    monkeypatch.setenv("OMW_HOME", str(home))
    db = home / "registry.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    root.mkdir()
    vault = registry.add_vault(
        db, name="v", path=root, type_="markdown", mode="wiki"
    )
    registry.set_active(db, "v")
    return db, root, vault["id"]


def _capture(db, root, *, session_id="s1", prompt, result, source="stop"):
    return session_capture.capture(
        db,
        {
            "session_id": session_id,
            "cwd": str(root),
            "prompt": prompt,
            "last_assistant_message": result,
        },
        host="codex",
        source=source,
    )


def test_schema_keeps_capture_shape_and_adds_candidate_tables(tmp_path, monkeypatch):
    db, _root, _vault_id = _db(tmp_path, monkeypatch)
    conn = registry.connect(db)
    try:
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        capture_cols = [row["name"] for row in conn.execute(
            "PRAGMA table_info(session_captures)"
        )]
    finally:
        conn.close()
    assert {
        "knowledge_candidate_batches", "knowledge_candidates",
        "knowledge_candidate_processed", "knowledge_candidate_scope_modes",
    } <= tables
    assert "candidate_processed_at" not in capture_cols


def test_default_mode_is_off_and_existing_capture_output_is_unchanged(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="검색 훅 구현", result="검색 훅 구현을 진행 중입니다."
    )

    assert knowledge_candidates.configured_mode() == "off"
    before = session_capture.list_captures(db)
    result = knowledge_candidates.process_pending(db, project_root=str(root))
    after = session_capture.list_captures(db)

    assert result == {"ok": True, "staged": False, "reason": "off"}
    assert before == after
    assert knowledge_candidates.list_batches(db) == []


def test_durable_decision_and_incident_make_one_deduplicated_batch(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db,
        root,
        prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.",
        result="장애의 근본 원인은 임계값 공유였고 전략별 기준으로 수정했다.",
    )

    first = knowledge_candidates.process_pending(
        db, project_root=str(root), session_id="s1", mode="staged"
    )
    second = knowledge_candidates.process_pending(
        db, project_root=str(root), session_id="s1", mode="staged"
    )

    assert first["staged"] is True and first["candidates"] == 2
    assert second["staged"] is False
    batches = knowledge_candidates.list_batches(db, project_root=str(root))
    assert len(batches) == 1
    shown = knowledge_candidates.show_batch(db, batches[0]["id"])
    assert {item["kind"] for item in shown["candidates"]} == {"decision", "incident"}


def test_ordinary_progress_chatter_produces_no_candidate(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="좋아 진행해", result="현재 테스트를 실행 중입니다. 잠시 기다려주세요."
    )

    result = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )

    assert result["staged"] is False and result["candidates"] == 0
    assert result["reason"] == "no durable signal survived the candidate policy"
    assert knowledge_candidates.list_batches(db) == []
    summary = knowledge_candidates.processing_summary(db)
    assert summary["processed"] == [{
        "outcome": "discarded",
        "reason": "no durable signal survived the candidate policy",
        "captures": 1,
    }]


def test_secret_bearing_capture_never_enters_candidate(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db,
        root,
        prompt="API_KEY=sk-secretvalue123456789 를 사용하기로 결정했다.",
        result="검증 완료했다.",
    )

    result = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )

    assert result["staged"] is False
    assert knowledge_candidates.list_batches(db) == []


def test_private_key_and_jwt_are_redacted_before_candidate_extraction(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    private_key = (
        "-----BEGIN PRIVATE KEY-----\nsecretmaterial\n-----END PRIVATE KEY-----"
    )
    jwt = "eyJabcdefghijk.abcdefghijklmnop.qrstuvwxyz12"
    _capture(
        db, root,
        prompt=f"이 키를 사용하기로 결정했다: {private_key}",
        result=f"검증 결과 토큰은 {jwt} 이다.",
    )

    result = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )

    assert result["staged"] is False
    assert knowledge_candidates.list_batches(db) == []


def test_speculation_generated_code_and_routine_logs_are_discarded(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    cases = (
        ("s1", "아마 근본 원인은 공유 임계값이라고 추측한다.", "아직 미확인이다."),
        ("s2", "```python\npolicy = '반드시 hybrid를 사용한다'\n```", "코드 생성 완료"),
        ("s3", "INFO 결정: 반드시 hybrid를 사용한다.", "DEBUG 검증 완료했다."),
    )
    for session_id, prompt, result in cases:
        _capture(db, root, session_id=session_id, prompt=prompt, result=result)
        staged = knowledge_candidates.process_pending(
            db, project_root=str(root), session_id=session_id, mode="staged"
        )
        assert staged["staged"] is False

    assert knowledge_candidates.list_batches(db) == []


def test_related_page_classifies_as_duplicate_or_update(tmp_path, monkeypatch):
    db, root, vault_id = _db(tmp_path, monkeypatch)
    page = root / "wiki" / "summaries" / "hybrid-search.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: Hybrid search policy\nsummary: 검색은 hybrid를 기본으로 사용한다.\n"
        "tags: [search]\nstatus: processed\n---\n\n검색은 hybrid를 기본으로 사용한다.\n",
        encoding="utf-8",
    )
    from scripts import reindex
    reindex.full(db, vault_id=vault_id)
    _capture(
        db, root, prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.", result="검증 완료했다."
    )

    result = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )
    item = knowledge_candidates.show_batch(db, result["batch_id"])["candidates"][0]

    assert item["classification"] in {"duplicate", "update"}
    assert item["matched_relpath"] == "wiki/summaries/hybrid-search.md"


def test_staged_mode_writes_nothing_until_explicit_approval(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.", result="검증 완료했다."
    )
    before = sorted(path.relative_to(root) for path in root.rglob("*"))

    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )
    after_stage = sorted(path.relative_to(root) for path in root.rglob("*"))
    approved = knowledge_candidates.approve_batch(db, batch_id=staged["batch_id"])

    assert after_stage == before
    assert approved["ok"] is True
    raw = root / approved["raw_relpath"]
    assert raw.is_file()
    text = raw.read_text(encoding="utf-8")
    assert "visibility: private" in text
    assert "candidate_batch_id:" in text
    assert knowledge_candidates.show_batch(db, staged["batch_id"])["status"] == "approved"


def test_partial_approvals_append_to_one_raw_record(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root,
        prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.",
        result="장애의 근본 원인은 임계값 공유였고 전략별 임계값으로 수정했다.",
    )
    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )
    items = knowledge_candidates.show_batch(db, staged["batch_id"])["candidates"]

    first = knowledge_candidates.approve_batch(
        db, batch_id=staged["batch_id"], item_ids=[items[0]["id"]]
    )
    second = knowledge_candidates.approve_batch(
        db, batch_id=staged["batch_id"], item_ids=[items[1]["id"]]
    )

    assert first["raw_relpath"] == second["raw_relpath"]
    text = (root / first["raw_relpath"]).read_text(encoding="utf-8")
    assert items[0]["content"] in text and items[1]["content"] in text
    assert knowledge_candidates.show_batch(db, staged["batch_id"])["status"] == "approved"


def test_same_pending_candidate_from_later_session_is_not_re_staged(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    kwargs = {
        "prompt": "검색은 hybrid를 기본으로 사용하기로 결정했다.",
        "result": "검증 완료했다.",
    }
    _capture(db, root, session_id="s1", **kwargs)
    first = knowledge_candidates.process_pending(
        db, project_root=str(root), session_id="s1", mode="staged"
    )
    _capture(db, root, session_id="s2", **kwargs)
    second = knowledge_candidates.process_pending(
        db, project_root=str(root), session_id="s2", mode="staged"
    )

    assert first["staged"] is True
    assert second["staged"] is False
    assert len(knowledge_candidates.list_batches(db)) == 1


def test_dismiss_never_writes_vault_file(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.", result="검증 완료했다."
    )
    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )

    result = knowledge_candidates.dismiss_batch(db, batch_id=staged["batch_id"])

    assert result["ok"] is True
    assert not (root / "raw").exists()
    assert knowledge_candidates.show_batch(db, staged["batch_id"])["status"] == "dismissed"


def test_precompact_processes_but_repeated_stop_only_captures(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    config.set_config("recall.session_capture", "on")
    config.set_config("recall.knowledge_candidates", "staged")
    payload = {
        "session_id": "s1", "cwd": str(root),
        "prompt": "hybrid를 기본으로 쓰기로 결정했다.",
        "last_assistant_message": "원인은 공유 임계값이었고 수정했다.",
    }
    monkeypatch.setattr("scripts.paths.registry_path", lambda: db)

    from scripts import recall
    stop = recall.capture_session(host="codex", source="stop", payload=payload)
    stop_again = recall.capture_session(host="codex", source="stop", payload=payload)
    compact = recall.capture_session(host="codex", source="precompact", payload=payload)

    assert stop["stored"] is True
    assert stop_again["reason"] == "duplicate"
    assert "candidate_batch" not in stop and "candidate_batch" not in stop_again
    assert compact["candidate_batch"]["staged"] is True
    assert len(knowledge_candidates.list_batches(db)) == 1


def test_cli_list_show_approve_round_trip(tmp_path, monkeypatch, capsys):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="hybrid를 기본으로 쓰기로 결정했다.", result="검증 완료했다."
    )
    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )
    from scripts import omw_cli

    assert omw_cli.main(["candidates", "list", "--project", str(root)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["id"] == staged["batch_id"]
    assert omw_cli.main(["candidates", "show", str(staged["batch_id"])]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["candidates"]
    assert omw_cli.main(["candidates", "approve", str(staged["batch_id"])]) == 0
    approved = json.loads(capsys.readouterr().out)
    assert (root / approved["raw_relpath"]).is_file()


def test_candidate_notice_frames_queue_without_exposing_content(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="hybrid를 기본으로 쓰기로 결정했다.", result="검증 완료했다."
    )
    knowledge_candidates.process_pending(db, project_root=str(root), mode="staged")

    notice = knowledge_candidates.render_notice(db, project_root=str(root))

    assert "omw candidates show" in notice
    assert "hybrid를 기본" not in notice
    assert "No vault page has been changed" in notice


def test_scoped_off_prevents_processing_even_when_global_is_staged(tmp_path, monkeypatch):
    db, root, vault_id = _db(tmp_path, monkeypatch)
    config.set_config("recall.knowledge_candidates", "staged")
    knowledge_candidates.set_scope_mode(
        db, scope_type="project", scope_value=str(root), mode="off"
    )
    _capture(
        db, root, prompt="hybrid를 기본으로 쓰기로 결정했다.", result="검증 완료했다."
    )

    mode = knowledge_candidates.effective_mode(
        db, project_root=str(root), host="codex", vault_id=vault_id
    )
    result = knowledge_candidates.process_pending(db, project_root=str(root))

    assert mode == "off"
    assert result["staged"] is False and result["reason"] == "off"
    assert knowledge_candidates.list_batches(db) == []


def test_cli_candidate_scope_config_and_status(tmp_path, monkeypatch, capsys):
    _db(tmp_path, monkeypatch)
    from scripts import omw_cli

    assert omw_cli.main([
        "candidates", "config", "--mode", "off", "--host", "codex"
    ]) == 0
    configured = json.loads(capsys.readouterr().out)
    assert configured["scope_type"] == "host"
    assert omw_cli.main(["candidates", "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["scope_modes"][0]["mode"] == "off"
    assert status["retention_days"] == 30


def test_old_pending_batch_expires_without_losing_audit_rows(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="hybrid를 기본으로 쓰기로 결정했다.", result="검증 완료했다."
    )
    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged"
    )
    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(timespec="seconds")
    conn = registry.connect(db)
    try:
        with conn:
            conn.execute(
                "UPDATE knowledge_candidate_batches SET created_at = ? WHERE id = ?",
                (old, staged["batch_id"]),
            )
    finally:
        conn.close()

    assert knowledge_candidates.list_batches(db) == []
    shown = knowledge_candidates.show_batch(db, staged["batch_id"])
    assert shown["status"] == "dismissed"
    assert shown["expired_at"]
    assert shown["candidates"][0]["status"] == "dismissed"
    summary = knowledge_candidates.processing_summary(db)
    assert summary["expired_batches"] == 1
    assert summary["processed"][0]["outcome"] == "staged"


def test_auto_raw_only_promotes_high_confidence_new_items(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db,
        root,
        prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.",
        result="측정 결과 이 설정은 검증되었다.",
    )

    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="auto-raw"
    )
    shown = knowledge_candidates.show_batch(db, staged["batch_id"])

    assert staged["auto_raw"]["ok"] is True
    assert (root / staged["auto_raw"]["raw_relpath"]).is_file()
    by_kind = {item["kind"]: item["status"] for item in shown["candidates"]}
    assert by_kind["decision"] == "approved"
    assert by_kind["fact"] == "pending"


def test_search_failure_is_never_auto_promoted(tmp_path, monkeypatch):
    db, root, _vault_id = _db(tmp_path, monkeypatch)
    _capture(
        db, root, prompt="검색은 hybrid를 기본으로 사용하기로 결정했다.", result="검증 완료했다."
    )
    monkeypatch.setattr(
        knowledge_candidates, "_search_hits",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("search unavailable")),
    )

    staged = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="auto-raw"
    )
    shown = knowledge_candidates.show_batch(db, staged["batch_id"])

    assert "auto_raw" not in staged
    assert shown["candidates"][0]["classification"] == "discard"
    assert not (root / "raw").exists()
