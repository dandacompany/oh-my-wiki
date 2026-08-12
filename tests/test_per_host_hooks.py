"""Per-platform hook wiring — each host's event names + stdout inject format differ.

Verified against local Codex 0.144.5 hook behavior (2026-07):
  claude/codex: SessionStart/UserPromptSubmit/PreToolUse/lifecycle hooks require JSON stdout.
  gemini:       SessionStart/BeforeAgent/BeforeTool/AfterAgent, JSON-envelope inject.
  hermes:       on_session_start/pre_llm_call/pre_tool_call/post_llm_call (YAML), {"context"}.
"""
import json

from scripts import gate, recall


# ── output adapter: omw recall <verb> --format <fmt> ─────────────────────────

def test_format_plain_is_bare_text():
    assert recall._format_output("hello", "plain", "SessionStart") == "hello"


def test_hook_binary_prefers_explicit_omw_bin(monkeypatch):
    monkeypatch.setenv("OMW_BIN", "/opt/omw/current")
    assert recall._omw_bin() == "/opt/omw/current"


def test_format_gemini_json_wraps_envelope():
    out = recall._format_output("ctx", "gemini-json", "BeforeAgent")
    obj = json.loads(out)
    assert obj["hookSpecificOutput"]["hookEventName"] == "BeforeAgent"
    assert obj["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_format_hermes_json_uses_context_key():
    obj = json.loads(recall._format_output("ctx", "hermes-json", "pre_llm_call"))
    assert obj == {"context": "ctx"}


def test_format_empty_output_is_noop():
    # JSON hosts reject blank stdout, so empty body must become a valid no-op.
    assert recall._format_output("", "plain", "SessionStart") == ""
    assert json.loads(recall._format_output("", "claude-json", "SessionStart")) == {"continue": True}
    assert json.loads(recall._format_output("", "codex-json", "SessionStart")) == {"continue": True}
    assert json.loads(recall._format_output("", "gemini-json", "BeforeAgent")) == {"continue": True}
    assert recall._format_output("", "hermes-json", "pre_llm_call") == ""


# ── recall hook wiring uses each host's concrete event names + format ────────

def test_gemini_wire_uses_gemini_event_names_and_json_format(tmp_path):
    cfg = tmp_path / "settings.json"
    changed, _ = recall.wire_host("gemini", config_path=cfg)
    assert changed
    data = json.loads(cfg.read_text())
    events = set(data["hooks"])
    # gemini injects on Session/BeforeAgent; BeforeTool injection is unconfirmed → not wired.
    assert {"SessionStart", "BeforeAgent"} <= events
    assert "UserPromptSubmit" not in events and "PreToolUse" not in events
    cmd = data["hooks"]["BeforeAgent"][0]["hooks"][0]["command"]
    assert "recall prompt" in cmd and "gemini-json" in cmd


def test_codex_wire_session_prompt_pretool_and_capture_hooks(tmp_path):
    cfg = tmp_path / "hooks.json"
    recall.wire_host("codex", config_path=cfg)
    data = json.loads(cfg.read_text())
    events = set(data["hooks"])
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse", "PreCompact", "Stop"} <= events
    cmd = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "recall prompt" in cmd and "codex-json" in cmd
    assert 'printf \'{\"continue\":true}' in cmd
    assert data["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 10
    assert data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] == 15
    assert "recall pretool" in data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert any("recall capture" in h["command"]
               for g in data["hooks"]["Stop"] for h in g["hooks"])
    assert any("recall capture" in h["command"]
               for g in data["hooks"]["PreCompact"] for h in g["hooks"])


def test_claude_wire_session_and_prompt_use_claude_json(tmp_path):
    cfg = tmp_path / "settings.json"
    recall.wire_host("claude", config_path=cfg)
    data = json.loads(cfg.read_text())
    for event in ("SessionStart", "UserPromptSubmit"):
        cmd = data["hooks"][event][0]["hooks"][0]["command"]
        assert "claude-json" in cmd
        assert 'printf \'{\"continue\":true}' in cmd


def test_claude_wires_pretool_as_claude_json(tmp_path):
    cfg = tmp_path / "settings.json"
    recall.wire_host("claude", config_path=cfg)
    data = json.loads(cfg.read_text())
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(data["hooks"])
    # Claude's PreToolUse injects via the JSON envelope, not plain text
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "recall pretool" in cmd and "claude-json" in cmd
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] == 5


def test_claude_wires_local_session_capture_without_replacing_other_stop_hooks(tmp_path):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "keep-stop.sh"}]},
    ]}}))

    recall.wire_host("claude", config_path=cfg)
    data = json.loads(cfg.read_text())
    stop_cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]

    assert "keep-stop.sh" in stop_cmds
    assert sum("recall capture" in cmd for cmd in stop_cmds) == 1
    assert "PreCompact" in data["hooks"]


def test_wire_migrates_stale_wrong_event_hooks(tmp_path):
    # a gemini config left with OLD Claude-named omw hooks must be cleaned on re-wire.
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {
        "UserPromptSubmit": [{"hooks": [{"type": "command",
                                         "command": '"omw" recall prompt'}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "keepme.sh"}]}],
    }}))
    changed, _ = recall.wire_host("gemini", config_path=cfg)
    assert changed
    data = json.loads(cfg.read_text())
    # stale omw hook under the wrong event is gone; non-omw hooks preserved
    assert "UserPromptSubmit" not in data["hooks"]
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "keepme.sh"
    assert "BeforeAgent" in data["hooks"]


def test_strip_preserves_user_hook_in_a_mixed_group(tmp_path):
    # a single group containing BOTH an omw hook and a user hook must keep the user hook.
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": '"omw" recall preamble'},
                   {"type": "command", "command": "user-thing.sh"}]}]}}))
    recall.wire_host("claude", config_path=cfg)
    data = json.loads(cfg.read_text())
    cmds = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    assert "user-thing.sh" in cmds                      # user hook survived
    assert sum("recall preamble" in c for c in cmds) == 1  # exactly one omw hook (no dup)


# ── gate (turn-end) stays Claude-only — no other host surfaces turn-end output ──

def test_gate_wires_claude_stop(tmp_path):
    cfg = tmp_path / "settings.json"
    changed, _ = gate.wire_host("claude", config_path=cfg)
    assert changed
    data = json.loads(cfg.read_text())
    assert "gate check" in data["hooks"]["Stop"][0]["hooks"][0]["command"]


def test_gate_skips_codex_and_gemini(tmp_path):
    # codex Stop / gemini AfterAgent don't surface turn-end output → no silent no-op hook.
    for host in ("codex", "gemini"):
        cfg = tmp_path / f"{host}.json"
        ok, _ = gate.wire_host(host, config_path=cfg)
        assert ok is False and not cfg.exists()


# ── P2: hermes YAML shell hooks ──────────────────────────────────────────────
import yaml  # noqa: E402


def test_wire_hermes_writes_pre_llm_call_with_context_format(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    changed, _ = recall.wire_hermes(config_path=cfg, allowlist_path=allow)
    assert changed
    data = yaml.safe_load(cfg.read_text())
    assert "pre_llm_call" in data["hooks"]
    cmd = data["hooks"]["pre_llm_call"][0]["command"]
    assert "recall prompt" in cmd and "hermes-json" in cmd and "--host hermes" in cmd
    capture = data["hooks"]["post_llm_call"][0]["command"]
    assert "recall capture" in capture and "--host hermes" in capture


def test_wire_hermes_preseeds_consent_allowlist(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    recall.wire_hermes(config_path=cfg, allowlist_path=allow)
    approvals = json.loads(allow.read_text())["approvals"]
    assert any(a["event"] == "pre_llm_call" and "recall prompt" in a["command"]
               for a in approvals)
    assert any(a["event"] == "post_llm_call" and "recall capture" in a["command"]
               for a in approvals)


def test_wire_hermes_recovers_non_object_consent_allowlist(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    allow.write_text("[]\n")

    recall.wire_hermes(config_path=cfg, allowlist_path=allow)

    data = json.loads(allow.read_text())
    assert isinstance(data, dict)
    assert {item["event"] for item in data["approvals"]} == {
        "pre_llm_call",
        "post_llm_call",
    }


def test_wire_hermes_idempotent_and_preserves(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    cfg.write_text(yaml.safe_dump({"model": {"default": "x"},
                                   "hooks": {"pre_tool_call": [{"command": "keep.sh"}]}}))
    changed1, _ = recall.wire_hermes(config_path=cfg, allowlist_path=allow)
    changed2, _ = recall.wire_hermes(config_path=cfg, allowlist_path=allow)
    assert changed1 is True and changed2 is False
    data = yaml.safe_load(cfg.read_text())
    assert data["model"]["default"] == "x"                       # preserved
    assert data["hooks"]["pre_tool_call"][0]["command"] == "keep.sh"  # preserved
    assert len(data["hooks"]["pre_llm_call"]) == 1               # not duplicated
    assert len(data["hooks"]["post_llm_call"]) == 1              # not duplicated


def test_wire_hermes_replaces_stale_omw_commands_only(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    cfg.write_text(yaml.safe_dump({
        "hooks": {
            "pre_llm_call": [
                {"command": '"old-omw" recall prompt --format hermes-json || true'},
                {"command": "keep-pre.sh"},
            ],
            "post_llm_call": [
                {"command": '"old-omw" recall capture --host hermes || true'},
                {"command": "keep-post.sh"},
            ],
        }
    }))
    allow.write_text(json.dumps({"approvals": [
        {"event": "pre_llm_call", "command": '"old-omw" recall prompt'},
        {"event": "pre_llm_call", "command": "keep-pre.sh"},
    ]}))

    changed, _ = recall.wire_hermes(config_path=cfg, allowlist_path=allow)

    assert changed is True
    data = yaml.safe_load(cfg.read_text())
    pre = [entry["command"] for entry in data["hooks"]["pre_llm_call"]]
    post = [entry["command"] for entry in data["hooks"]["post_llm_call"]]
    assert pre.count("keep-pre.sh") == 1 and any("--host hermes" in cmd for cmd in pre)
    assert post.count("keep-post.sh") == 1 and any("--source stop" in cmd for cmd in post)
    approvals = json.loads(allow.read_text())["approvals"]
    assert any(item["command"] == "keep-pre.sh" for item in approvals)
    assert not any("old-omw" in item["command"] for item in approvals)


def test_wire_hermes_honors_hermes_home_for_config_and_allowlist(tmp_path, monkeypatch):
    home = tmp_path / "opt" / "data"
    (home / "profiles" / "oliver").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    changed, _ = recall.wire_hermes(profile="oliver")

    assert changed is True
    cfg = home / "profiles" / "oliver" / "config.yaml"
    allow = home / "shell-hooks-allowlist.json"
    assert "pre_llm_call" in yaml.safe_load(cfg.read_text())["hooks"]
    assert json.loads(allow.read_text())["approvals"]


# ── P3: opencode + openclaw TS plugins ───────────────────────────────────────

def test_wire_opencode_writes_plugin_file(tmp_path):
    dest = tmp_path / "plugin" / "omw-recall.ts"
    changed, _ = recall.wire_ts_plugin("opencode", dest=dest)
    assert changed and dest.exists()
    src = dest.read_text()
    # uses the experimental system-prompt transform (the only opencode inject surface)
    assert "omw" in src and "recall" in src
    assert "experimental.chat.system.transform" in src


def test_wire_openclaw_writes_plugin_and_registers(tmp_path):
    dest = tmp_path / "plugins" / "omw-recall" / "index.ts"
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps({"plugins": {"entries": {}}, "gateway": {"token": "KEEP"}}))
    changed, _ = recall.wire_ts_plugin("openclaw", dest=dest, config_path=cfg)
    assert changed and dest.exists()
    src = dest.read_text()
    assert "before_prompt_build" in src and "prependContext" in src
    reg = json.loads(cfg.read_text())
    assert reg["plugins"]["entries"]["omw-recall"]["enabled"] is True
    assert reg["gateway"]["token"] == "KEEP"  # preserved


def test_wire_ts_plugin_idempotent(tmp_path):
    dest = tmp_path / "plugin" / "omw-recall.ts"
    recall.wire_ts_plugin("opencode", dest=dest)
    changed2, _ = recall.wire_ts_plugin("opencode", dest=dest)
    assert changed2 is False  # already present


def test_openclaw_registers_even_when_plugin_file_preexists(tmp_path):
    # B5: a pre-existing plugin file must not leave openclaw.json unregistered.
    dest = tmp_path / "plugins" / "omw-recall" / "index.ts"
    dest.parent.mkdir(parents=True)
    dest.write_text("// omw-recall (pre-existing)\n")
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps({"plugins": {"entries": {}}, "gateway": {"token": "T"}}))
    changed, _ = recall.wire_ts_plugin("openclaw", dest=dest, config_path=cfg)
    assert changed  # registration happened despite the file already existing
    reg = json.loads(cfg.read_text())
    assert reg["plugins"]["entries"]["omw-recall"]["enabled"] is True
    assert reg["gateway"]["token"] == "T"
