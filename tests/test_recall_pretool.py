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
