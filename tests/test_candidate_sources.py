import json

from scripts import candidate_sources, knowledge_candidates, registry, session_capture


def test_agentmemory_export_keeps_summary_and_only_important_observations(tmp_path):
    export = tmp_path / "agentmemory.json"
    export.write_text(json.dumps({
        "session": {"summary": "검색은 hybrid를 기본으로 사용하기로 결정했다."},
        "observations": [
            {"content": "근본 원인은 공유 임계값이었고 수정했다.", "importance": 0.9},
            {"content": "현재 테스트 실행 중", "importance": 0.2},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    evidence = candidate_sources.load_agentmemory_export(export)

    assert len(evidence) == 2
    assert all("테스트 실행 중" not in item for item in evidence)


def test_agentmemory_export_redacts_secret_bearing_observation(tmp_path):
    export = tmp_path / "agentmemory.json"
    export.write_text(json.dumps({
        "observations": [{
            "content": "API_KEY=sk-secretvalue123456789 를 사용하기로 결정했다.",
            "important": True,
        }],
    }, ensure_ascii=False), encoding="utf-8")

    assert candidate_sources.load_agentmemory_export(export) == []


def test_agentmemory_export_rejects_oversized_file_before_parsing(tmp_path):
    export = tmp_path / "agentmemory.json"
    export.write_bytes(b" " * (candidate_sources._MAX_EXPORT_BYTES + 1))

    assert candidate_sources.load_agentmemory_export(export) == []


def test_agentmemory_evidence_joins_existing_capture_batch(tmp_path, monkeypatch):
    home = tmp_path / ".omw"
    monkeypatch.setenv("OMW_HOME", str(home))
    db = home / "registry.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    root.mkdir()
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    registry.set_active(db, "v")
    session_capture.capture(db, {
        "session_id": "s1", "cwd": str(root),
        "prompt": "작업을 정리해줘", "last_assistant_message": "완료했습니다.",
    }, host="codex", source="stop")
    export = tmp_path / "agentmemory.json"
    export.write_text(json.dumps({
        "summary": "검색은 hybrid를 기본으로 사용하기로 결정했다."
    }, ensure_ascii=False), encoding="utf-8")

    result = knowledge_candidates.process_pending(
        db, project_root=str(root), mode="staged", agentmemory_json=export,
    )
    batch = knowledge_candidates.show_batch(db, result["batch_id"])

    assert result["staged"] is True
    assert batch["candidates"][0]["provenance"]["origin"] == "agentmemory"
    assert batch["candidates"][0]["provenance"]["agentmemory_export"] == str(export.resolve())
