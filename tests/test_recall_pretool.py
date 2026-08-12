from scripts import recall


def _has_active(monkeypatch, yes=True):
    class _DB:
        def exists(self):
            return True
    monkeypatch.setattr("scripts.paths.registry_path", lambda: _DB())
    monkeypatch.setattr(recall, "_active",
                        lambda db: {"id": 1, "name": "v"} if yes else None)


def test_pretool_nudges_on_raw_grep(monkeypatch):
    _has_active(monkeypatch, True)
    out = recall.pretool({"tool_name": "Grep",
                          "tool_input": {"pattern": "ARIMA", "path": "raw/"}})
    assert "omw find" in out and recall.MARKER in out
    assert not any("가" <= char <= "힣" for char in out)


def test_pretool_silent_without_wiki(monkeypatch):
    _has_active(monkeypatch, False)
    out = recall.pretool({"tool_name": "Read",
                          "tool_input": {"file_path": "raw/x.md"}})
    assert out == ""


def test_pretool_silent_on_unrelated_tool(monkeypatch):
    _has_active(monkeypatch, True)
    out = recall.pretool({"tool_name": "Bash",
                          "tool_input": {"command": "ls"}})
    assert out == ""


def test_pretool_supports_codex_exec_command(monkeypatch):
    _has_active(monkeypatch, True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [{
        "relpath": "wiki/recall-hooks.md", "title": "Recall hooks", "score": 8.0}])
    out = recall.pretool({
        "tool_name": "exec_command",
        "tool_input": {"cmd": "sed -n '1,80p' scripts/recall.py"},
    })
    assert "Related wiki pages" in out and "wiki/recall-hooks.md" in out


def test_pretool_codex_command_detects_raw(monkeypatch):
    _has_active(monkeypatch, True)
    monkeypatch.setattr(recall, "_pretool_path_hits", lambda payload: [])
    out = recall.pretool({
        "tool_name": "exec_command",
        "tool_input": {"cmd": "rg hook raw/claude-code.md"},
    })
    assert "omw find" in out
