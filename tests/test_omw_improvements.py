"""Tests for the UX-friction fixes (F1, F2, F3, F7) found during install/codex dogfooding."""
import json

from scripts import agent_skills, setup_wizard
from scripts.viewers import base
from scripts.viewers.obsidian import ObsidianViewer


# --- F7: Obsidian vault registration -------------------------------------------------

def test_register_vault_adds_entry_and_is_idempotent(tmp_path):
    cfg = tmp_path / "obsidian.json"
    cfg.write_text(json.dumps({"vaults": {"abc": {"path": "/other"}}}), encoding="utf-8")
    root = tmp_path / "myvault"

    assert ObsidianViewer  # sanity
    from scripts.viewers import obsidian
    assert obsidian.vault_registered(root, config_path=cfg) is False
    assert obsidian.register_vault(root, config_path=cfg) is True
    assert obsidian.vault_registered(root, config_path=cfg) is True
    # existing entry preserved
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert any(v["path"] == "/other" for v in data["vaults"].values())
    # second call is a no-op
    assert obsidian.register_vault(root, config_path=cfg) is False


def test_register_vault_creates_config_when_absent(tmp_path):
    from scripts.viewers import obsidian
    cfg = tmp_path / "sub" / "obsidian.json"
    root = tmp_path / "v"
    assert obsidian.register_vault(root, config_path=cfg) is True
    assert cfg.is_file()
    assert obsidian.vault_registered(root, config_path=cfg) is True


def test_preflight_warns_when_unregistered(tmp_path, monkeypatch):
    from scripts.viewers import obsidian
    cfg = tmp_path / "obsidian.json"
    monkeypatch.setattr(obsidian, "app_config_path", lambda: cfg)
    v = base.VaultRef(root=tmp_path / "vault", name="vault")
    hints = ObsidianViewer().preflight(v)
    assert any("Open folder as vault" in h for h in hints)
    # now registered → no warning
    assert ObsidianViewer().preflight(v) == []


# --- F2: skills-cli dest parsing -----------------------------------------------------

def test_parse_skills_cli_dest_extracts_path():
    out = (
        "\x1b[?25l│\n"
        "◇  Installed 1 skill\n"
        "│  ✓ oh-my-wiki (copied)\n"
        "│    → ~/work/proj/.agents/skills/oh-my-wiki  │\n"  # trailing box border
        "└  Done!\n"
    )
    assert agent_skills._parse_skills_cli_dest(out) == "~/work/proj/.agents/skills/oh-my-wiki"


def test_parse_skills_cli_dest_none_when_absent():
    assert agent_skills._parse_skills_cli_dest("no path here") is None


# --- F3: select fallback shows choices ----------------------------------------------

def test_select_fallback_lists_choices(monkeypatch):
    captured = {}

    def fake_input(prompt):
        captured["prompt"] = prompt
        return ""  # accept default

    # force the questionary-absent path
    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setitem(__import__("sys").modules, "questionary", None)
    got = setup_wizard._prompt("select", "TTS provider", choices=["elevenlabs", "skip"], default="elevenlabs")
    assert got == "elevenlabs"
    assert "elevenlabs" in captured["prompt"] and "skip" in captured["prompt"]


# --- recall engine (host-agnostic) ---------------------------------------------------

def test_recall_is_trivial():
    from scripts import recall
    assert recall.is_trivial("ok") is True
    assert recall.is_trivial("고마워") is True
    assert recall.is_trivial("  ") is True
    assert recall.is_trivial("수요 예측에서 평가지표는?") is False


def test_recall_prompt_off_mode_silent(monkeypatch):
    from scripts import recall
    monkeypatch.setattr(recall, "_cfg", lambda: {"mode": "off", "min_score": 1.0, "top_k": 3, "snippet_chars": 280})
    assert recall.prompt("수요 예측 평가지표 MAPE 알려줘") == ""


def test_recall_prompt_auto_injects_strong_hit(monkeypatch):
    from scripts import recall
    monkeypatch.setattr(recall, "_cfg", lambda: {"mode": "auto", "min_score": 1.0, "top_k": 3, "snippet_chars": 280})
    monkeypatch.setattr(recall, "_hits", lambda text, k: [
        {"title": "Demand Forecasting", "relpath": "wiki/syntheses/demand-forecasting.md",
         "tags": ["arima"], "score": 1.42},
    ])
    out = recall.prompt("수요 예측 평가지표 MAPE 알려줘")
    assert "<omw-recall>" in out and "demand-forecasting.md" in out


def test_recall_prompt_auto_silent_on_weak_hit(monkeypatch):
    from scripts import recall
    monkeypatch.setattr(recall, "_cfg", lambda: {"mode": "auto", "min_score": 2.0, "top_k": 3, "snippet_chars": 280})
    monkeypatch.setattr(recall, "_hits", lambda text, k: [{"title": "X", "relpath": "a.md", "tags": [], "score": 0.5}])
    assert recall.prompt("이 도메인 사실을 알려줘 길게길게") == ""


def test_recall_prompt_advisory_nudges_without_hit(monkeypatch):
    from scripts import recall
    monkeypatch.setattr(recall, "_cfg", lambda: {"mode": "advisory", "min_score": 9.0, "top_k": 3, "snippet_chars": 280})
    monkeypatch.setattr(recall, "_hits", lambda text, k: [])
    out = recall.prompt("프로젝트 도메인 사실 질문입니다 길게")
    assert "omw find" in out


def test_recall_block_and_upsert_idempotent(tmp_path):
    from scripts import recall
    md = tmp_path / "AGENTS.md"
    md.write_text("# head\n\nbody\n", encoding="utf-8")
    block = recall.render_recall_block("auto")
    assert "omw-recall:start" in block and "auto" in block
    recall.upsert_block(md, block)
    recall.upsert_block(md, block)  # idempotent
    text = md.read_text(encoding="utf-8")
    assert text.count("omw-recall:start") == 1
    assert "# head" in text and "body" in text


# --- F6: autoresearch synthesis gets a summary (lifts recall/index) ------------------

def test_derive_summary_skips_headings_and_claims():
    from scripts import autoresearch
    body = "# Demand Forecasting\n\n**Claim 1 — confidence: high.** x\n\n수요 예측은 과거 데이터로 미래를 추정한다.\n"
    s = autoresearch._derive_summary(body)
    assert s.startswith("수요 예측은")
    assert "#" not in s and "Claim" not in s


def test_derive_summary_truncates():
    from scripts import autoresearch
    long = "가" * 500
    s = autoresearch._derive_summary("\n\n" + long, cap=240)
    assert len(s) <= 241 and s.endswith("…")


def test_write_synthesis_includes_summary(tmp_path):
    from scripts import frontmatter, query, registry
    from scripts.paths import registry_path
    # minimal vault registered in a temp OMW_HOME
    import os
    os.environ["OMW_HOME"] = str(tmp_path / "home")
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "v"
    (root / "wiki" / "syntheses").mkdir(parents=True)
    v = registry.add_vault(db, name="t", path=root, type_="markdown", mode="wiki")
    rel = query.write_synthesis(db, vault_id=v["id"], title="Demand X", body="본문 첫 문단.",
                                citations=["http://a"], tags=["x"], date_str="2026-06-18",
                                summary="요약 문장")
    meta, _ = frontmatter.parse((root / rel).read_text(encoding="utf-8"))
    assert meta.get("summary") == "요약 문장"
    os.environ.pop("OMW_HOME", None)


# --- host hook wiring (claude/codex/gemini all share the schema) ---------------------

def test_prompt_from_stdin_extracts_json_prompt():
    from scripts import recall
    assert recall._prompt_from_stdin('{"prompt": "수요 예측 평가지표"}') == "수요 예측 평가지표"
    assert recall._prompt_from_stdin('{"session_id":"x","user_prompt":"hello there"}') == "hello there"
    assert recall._prompt_from_stdin("raw text fallback here") == "raw text fallback here"
    assert recall._prompt_from_stdin('{"unrelated": 1}') == ""


def test_wire_host_is_idempotent_and_preserves(tmp_path):
    import json
    from scripts import recall
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({
        "mcpServers": {"x": {"command": "y"}},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "existing.sh"}]}]},
    }), encoding="utf-8")

    changed, _ = recall.wire_host("claude", config_path=cfg)
    assert changed is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    # preserved unrelated config + existing hook
    assert data["mcpServers"]["x"]["command"] == "y"
    cmds = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    assert "existing.sh" in cmds
    assert any("recall preamble" in c for c in cmds)
    assert any("recall prompt" in h["command"]
               for g in data["hooks"]["UserPromptSubmit"] for h in g["hooks"])
    # backup written
    assert cfg.with_suffix(".json.omw-bak").exists()

    # second run is a no-op
    changed2, detail2 = recall.wire_host("claude", config_path=cfg)
    assert changed2 is False and "already wired" in detail2


def test_recall_normalize_query_strips_josa():
    from scripts import recall
    assert recall._strip_josa("ARIMA와") == "ARIMA"
    assert recall._strip_josa("평가지표를") == "평가지표"
    assert recall._strip_josa("수요예측에서") == "수요예측"
    assert recall._strip_josa("prophet") == "prophet"   # no Hangul tail
    assert recall._strip_josa("가") == "가"             # too short after strip
    assert recall.normalize_query("수요예측에서 ARIMA와 Prophet 차이를") == "수요예측 ARIMA Prophet 차이"


def test_recall_effective_strategy_falls_back(capsys):
    from scripts import recall
    assert recall.effective_strategy("fts") == "fts"
    assert recall.effective_strategy("embedding") == "fts"   # planned → fts
    assert recall.effective_strategy("hybrid") == "fts"
    assert recall.effective_strategy("nonsense") == "fts"
    err = capsys.readouterr().err
    assert "planned" in err  # the implemented-but-not-yet strategies announce fallback


def test_recall_cost_warning_only_for_auto_llm():
    from scripts import recall
    assert recall.cost_warning("auto", "llm") is not None
    assert recall.cost_warning("advisory", "llm") is None
    assert recall.cost_warning("auto", "fts") is None


def test_recall_cfg_reads_strategy_and_submode(tmp_path, monkeypatch):
    import os
    from scripts import config, recall
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "home"))
    config.set_config("recall.mode", "advisory")
    config.set_config("recall.strategy", "llm")
    config.set_config("recall.llm.submode", "generative")
    cfg = recall._cfg()
    assert cfg["mode"] == "advisory" and cfg["strategy"] == "llm" and cfg["llm_submode"] == "generative"
    os.environ.pop("OMW_HOME", None)


def test_wire_host_creates_config_when_absent(tmp_path):
    import json
    from scripts import recall
    cfg = tmp_path / "sub" / "hooks.json"
    changed, _ = recall.wire_host("codex", config_path=cfg)
    assert changed is True and cfg.is_file()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "UserPromptSubmit" in data["hooks"] and "SessionStart" in data["hooks"]
