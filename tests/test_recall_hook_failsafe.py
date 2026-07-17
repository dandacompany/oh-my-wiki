"""Recall hooks must NEVER block a host session or emit invalid JSON.

The generated hook command must turn argument drift, empty recall output, and
malformed stdout into the host's valid no-op object rather than leaking blank or
plain stdout into a JSON hook contract.
"""
import json
import subprocess

from scripts import recall


def test_json_hook_commands_are_failsafe_and_json_safe():
    for host in ("claude", "codex", "gemini"):
        specs = recall._recall_hook_specs(host)
        assert specs, f"{host} should have recall hook events"
        for event, (cmd, _status, timeout) in specs.items():
            assert " recall " in cmd, (host, event, cmd)
            assert "rc=$?" in cmd, (host, event, cmd)
            assert "jq -e ." in cmd, (host, event, cmd)
            assert '{\"continue\":true}' in cmd, (host, event, cmd)
            expected = {
                "UserPromptSubmit": 15,
                "BeforeAgent": 15,
                "PreToolUse": 5,
            }.get(event, 10)
            assert timeout == expected, (host, event, timeout)


def _run_session_hook(monkeypatch, binary):
    monkeypatch.setattr(recall, "_omw_bin", lambda: str(binary))
    cmd, _status, _timeout = recall._recall_hook_specs("codex")["SessionStart"]
    return subprocess.run(cmd, shell=True, input="{}", text=True,
                          capture_output=True, check=False)


def _fake_hook(tmp_path, body):
    path = tmp_path / "fake-omw"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_missing_binary_becomes_valid_noop(monkeypatch, tmp_path):
    result = _run_session_hook(monkeypatch, tmp_path / "missing-omw")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"continue": True}


def test_empty_and_malformed_stdout_become_valid_noop(monkeypatch, tmp_path):
    for body in ("exit 0\n", "printf 'not-json\\n'\n"):
        result = _run_session_hook(monkeypatch, _fake_hook(tmp_path, body))
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"continue": True}


def test_valid_json_survives_and_stderr_stays_separate(monkeypatch, tmp_path):
    payload = {"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": "ctx"}}
    body = ("printf 'diagnostic\\n' >&2\n"
            f"printf '%s\\n' '{json.dumps(payload)}'\n")
    result = _run_session_hook(monkeypatch, _fake_hook(tmp_path, body))
    assert result.returncode == 0
    assert json.loads(result.stdout) == payload
    assert result.stderr == "diagnostic\n"
