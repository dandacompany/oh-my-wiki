"""Tests for setup_recall host-picker (Task 4: convention choices + dedup write)."""
from scripts import setup_wizard


def test_setup_recall_merged_agents_written_once(tmp_path, monkeypatch):
    """codex + opencode both resolve to AGENTS.md — recall block should appear exactly once."""
    rc = setup_wizard.setup_recall(noninteractive=True, base_dir=str(tmp_path),
                                   hosts=["codex", "opencode"], mode="auto", strategy="fts")
    assert rc == 0
    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("<!-- omw-recall:start -->") == 1
