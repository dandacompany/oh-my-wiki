import json

from scripts import uninstall


def test_is_omw_recall_cmd():
    assert uninstall._is_omw_recall_cmd('"omw" recall prompt') is True
    assert uninstall._is_omw_recall_cmd('"/usr/bin/omw" recall pretool') is True
    assert uninstall._is_omw_recall_cmd('"omw" recall capture --source stop') is True
    assert uninstall._is_omw_recall_cmd("my-other-tool run") is False
    assert uninstall._is_omw_recall_cmd("recall something else") is False  # no subcommand


def test_strip_hooks_removes_only_omw(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({
        "model": "opus",
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": '"omw" recall prompt'}]},
                {"hooks": [{"type": "command", "command": "my-linter --check"}]},
            ],
            "SessionStart": [
                {"hooks": [{"type": "command", "command": '"omw" recall preamble'}]},
            ],
            "PreCompact": [
                {"hooks": [{"type": "command",
                            "command": '"omw" recall capture --source precompact'}]},
            ],
        },
    }, indent=2), encoding="utf-8")
    removed, changed = uninstall._strip_omw_hooks(cfg)
    assert changed is True
    assert removed == 3
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["model"] == "opus"                       # unrelated key preserved
    assert len(data["hooks"]["UserPromptSubmit"]) == 1   # user linter kept
    assert data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == "my-linter --check"
    assert "SessionStart" not in data["hooks"]            # emptied event dropped
    assert "PreCompact" not in data["hooks"]              # capture hook removed too


def test_strip_hooks_drops_empty_hooks_key(tmp_path):
    cfg = tmp_path / "hooks.json"
    cfg.write_text(json.dumps({
        "hooks": {"PreToolUse": [
            {"hooks": [{"type": "command", "command": '"omw" recall pretool'}]}]},
    }, indent=2), encoding="utf-8")
    removed, changed = uninstall._strip_omw_hooks(cfg)
    assert changed and removed == 1
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "hooks" not in data


def test_strip_hooks_noop_when_absent(tmp_path):
    assert uninstall._strip_omw_hooks(tmp_path / "nope.json") == (0, False)


def test_strip_hooks_noop_when_no_omw(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"X": [{"hooks": [{"command": "other"}]}]}}), encoding="utf-8")
    assert uninstall._strip_omw_hooks(cfg) == (0, False)


def test_strip_hooks_survives_nondict_hook_entry(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"X": [{"hooks": [42, "weird", None]}]}}), encoding="utf-8")
    # must not raise; nothing matches → no-op
    assert uninstall._strip_omw_hooks(cfg) == (0, False)
