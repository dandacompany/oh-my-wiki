import json
import os
import subprocess
import sys

import pytest

from scripts import config, registry


def _runtime(tmp_path, monkeypatch):
    home = tmp_path / ".omw"
    monkeypatch.setenv("OMW_HOME", str(home))
    db = home / "registry.db"
    registry.init_db(db)
    root = tmp_path / "project"
    root.mkdir()
    vault = registry.add_vault(
        db, name="v", path=root, type_="markdown", mode="wiki"
    )
    registry.set_active(db, "v")
    config.set_config("recall.session_capture", "on")
    config.set_config("recall.knowledge_candidates", "staged")
    env = os.environ.copy()
    env["OMW_HOME"] = str(home)
    return db, root, vault["id"], env


def _run(env, args, payload):
    return subprocess.run(
        [sys.executable, "-m", "scripts.omw_cli", *args],
        input=json.dumps(payload, ensure_ascii=False), text=True,
        capture_output=True, env=env, check=False,
    )


@pytest.mark.parametrize(
    ("host", "fmt"), [("claude", "claude-json"), ("codex", "codex-json")]
)
def test_json_host_real_process_stop_then_precompact_stages_once(
    tmp_path, monkeypatch, host, fmt,
):
    db, root, _vault_id, env = _runtime(tmp_path, monkeypatch)
    payload = {
        "session_id": f"{host}-session", "cwd": str(root),
        "prompt": "검색은 hybrid를 기본으로 사용하기로 결정했다.",
        "last_assistant_message": "근본 원인은 공유 임계값이었고 수정했다.",
    }
    stop = _run(env, [
        "recall", "capture", "--format", fmt, "--event", "Stop",
        "--host", host, "--source", "stop",
    ], payload)
    compact = _run(env, [
        "recall", "capture", "--format", fmt, "--event", "PreCompact",
        "--host", host, "--source", "precompact",
    ], payload)

    assert stop.returncode == 0 and json.loads(stop.stdout) == {"continue": True}
    assert compact.returncode == 0 and json.loads(compact.stdout) == {"continue": True}
    conn = registry.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM knowledge_candidate_batches").fetchone()[0] == 1
    finally:
        conn.close()


def test_hermes_yaml_hook_real_process_captures_without_blocking(tmp_path, monkeypatch):
    db, root, _vault_id, env = _runtime(tmp_path, monkeypatch)
    payload = {
        "session_id": "hermes-session", "cwd": str(root),
        "prompt": "검색은 hybrid를 기본으로 사용하기로 결정했다.",
        "last_assistant_message": "검증 완료했다.",
    }

    result = _run(env, [
        "recall", "capture", "--format", "hermes-json", "--event", "post_llm_call",
        "--host", "hermes", "--source", "stop",
    ], payload)

    assert result.returncode == 0 and result.stdout == ""
    conn = registry.connect(db)
    try:
        row = conn.execute("SELECT host, session_id FROM session_captures").fetchone()
        assert tuple(row) == ("hermes", "hermes-session")
        # Turn-end remains cheap: it captures but does not classify every turn.
        assert conn.execute("SELECT COUNT(*) FROM knowledge_candidate_batches").fetchone()[0] == 0
    finally:
        conn.close()

    next_prompt = {
        "session_id": "hermes-next", "cwd": str(root), "host": "hermes",
        "prompt": "다음 작업을 시작하자",
    }
    recalled = _run(env, [
        "recall", "prompt", "--format", "hermes-json", "--event", "pre_llm_call",
        "--host", "hermes",
    ], next_prompt)
    assert recalled.returncode == 0
    assert "omw candidates show" in recalled.stdout
    conn = registry.connect(db)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_candidate_batches"
        ).fetchone()[0] == 1
    finally:
        conn.close()


def test_next_session_start_stages_previous_session_and_emits_bounded_notice(
    tmp_path, monkeypatch,
):
    db, root, _vault_id, env = _runtime(tmp_path, monkeypatch)
    prior = {
        "session_id": "prior-session", "cwd": str(root),
        "prompt": "검색은 hybrid를 기본으로 사용하기로 결정했다.",
        "last_assistant_message": "근본 원인은 공유 임계값이었고 수정했다.",
    }
    stop = _run(env, [
        "recall", "capture", "--format", "codex-json", "--event", "Stop",
        "--host", "codex", "--source", "stop",
    ], prior)
    current = {"session_id": "new-session", "cwd": str(root), "host": "codex"}
    start = _run(env, [
        "recall", "preamble", "--format", "codex-json", "--event", "SessionStart",
        "--host", "codex",
    ], current)

    assert stop.returncode == 0 and start.returncode == 0
    envelope = json.loads(start.stdout)
    rendered = json.dumps(envelope, ensure_ascii=False)
    assert "omw candidates show" in rendered
    notice = rendered.split("<omw-candidates>", 1)[1]
    assert "hybrid를 기본" not in notice
    conn = registry.connect(db)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM knowledge_candidate_batches"
        ).fetchone()[0] == 1
    finally:
        conn.close()
