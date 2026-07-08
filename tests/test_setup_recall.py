"""Tests for setup_recall host-picker (Task 4: convention choices + dedup write)."""
from scripts import config, setup_wizard


def test_setup_recall_merged_agents_written_once(tmp_path, monkeypatch):
    """codex + opencode both resolve to AGENTS.md — recall block should appear exactly once."""
    rc = setup_wizard.setup_recall(noninteractive=True, base_dir=str(tmp_path),
                                   hosts=["codex", "opencode"], mode="auto", strategy="fts")
    assert rc == 0
    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("<!-- omw-recall:start -->") == 1


def test_setup_recall_noninteractive_switches_normalizer(monkeypatch, tmp_path):
    from scripts import setup_wizard
    calls = {}
    monkeypatch.setattr(setup_wizard, "_normalize_admin_switch",
                        lambda db, provider, *, assume_yes: calls.update(provider=provider) or
                        {"ok": True, "provider": provider, "vaults_reindexed": 0, "detail": None})
    # minimal recall config path: mode auto, strategy fts, normalizer kiwi
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", normalizer="kiwi",
                                   hosts=[], noninteractive=True, base_dir=str(tmp_path))
    assert rc == 0
    assert calls.get("provider") == "kiwi"


def test_configure_recall_writes_capture_toggle():
    setup_wizard.configure_recall(strategy="fts", capture=True, noninteractive=True)
    assert config.load_config()["recall"]["capture"] == "on"
    setup_wizard.configure_recall(strategy="fts", capture=False, noninteractive=True)
    assert config.load_config()["recall"]["capture"] == "off"


def test_configure_recall_mem0_preset():
    setup_wizard.configure_recall(mem0_preset=True, noninteractive=True)
    rc = config.load_config()["recall"]
    assert rc["mode"] == "advisory"
    assert rc["strategy"] == "llm"
    assert rc["capture"] == "on"
