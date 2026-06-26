"""Per-platform hook wiring — each host's event names + stdout inject format differ.

Verified against official docs (2026-06):
  claude/codex: SessionStart/UserPromptSubmit/PreToolUse/Stop, plain stdout inject.
  gemini:       SessionStart/BeforeAgent/BeforeTool/AfterAgent, JSON-envelope inject.
  hermes:       on_session_start/pre_llm_call/pre_tool_call/post_llm_call (YAML), {"context"}.
"""
import json

from scripts import gate, recall


# ── output adapter: omw recall <verb> --format <fmt> ─────────────────────────

def test_format_plain_is_bare_text():
    assert recall._format_output("hello", "plain", "SessionStart") == "hello"


def test_format_gemini_json_wraps_envelope():
    out = recall._format_output("ctx", "gemini-json", "BeforeAgent")
    obj = json.loads(out)
    assert obj["hookSpecificOutput"]["hookEventName"] == "BeforeAgent"
    assert obj["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_format_hermes_json_uses_context_key():
    obj = json.loads(recall._format_output("ctx", "hermes-json", "pre_llm_call"))
    assert obj == {"context": "ctx"}


def test_format_empty_output_is_noop():
    # empty body → no injection (empty string), never a malformed envelope
    assert recall._format_output("", "plain", "SessionStart") == ""
    assert recall._format_output("", "gemini-json", "BeforeAgent") == ""
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


def test_codex_wire_session_prompt_plain_no_pretool(tmp_path):
    cfg = tmp_path / "hooks.json"
    recall.wire_host("codex", config_path=cfg)
    data = json.loads(cfg.read_text())
    events = set(data["hooks"])
    assert {"SessionStart", "UserPromptSubmit"} <= events
    assert "PreToolUse" not in events  # codex doesn't inject on pre-tool → not wired
    cmd = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "recall prompt" in cmd and "plain" in cmd


def test_claude_wires_pretool_as_claude_json(tmp_path):
    cfg = tmp_path / "settings.json"
    recall.wire_host("claude", config_path=cfg)
    data = json.loads(cfg.read_text())
    assert {"SessionStart", "UserPromptSubmit", "PreToolUse"} <= set(data["hooks"])
    # Claude's PreToolUse injects via the JSON envelope, not plain text
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "recall pretool" in cmd and "claude-json" in cmd


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
    assert "recall prompt" in cmd and "hermes-json" in cmd


def test_wire_hermes_preseeds_consent_allowlist(tmp_path):
    cfg = tmp_path / "config.yaml"
    allow = tmp_path / "allow.json"
    recall.wire_hermes(config_path=cfg, allowlist_path=allow)
    approvals = json.loads(allow.read_text())["approvals"]
    assert any(a["event"] == "pre_llm_call" and "recall prompt" in a["command"]
               for a in approvals)


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
