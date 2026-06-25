from pathlib import Path

from scripts import hosts


def test_instruction_choices_merges_codex_opencode():
    choices = hosts.instruction_choices()
    labels = {c["key"]: c for c in choices}
    # codex + opencode share AGENTS.md → one convention choice "agents"
    assert "agents" in labels and set(labels["agents"]["members"]) == {"codex", "opencode"}
    assert labels["agents"]["file"] == "AGENTS.md"
    assert labels["claude"]["file"] == "CLAUDE.md"
    assert labels["gemini"]["file"] == "GEMINI.md"
    assert labels["hermes"]["scoped"] is True and labels["openclaw"]["scoped"] is True
    assert labels["claude"]["scoped"] is False


def test_resolve_repo_paths_share_agents(tmp_path):
    assert hosts.resolve_instruction_path("codex", tmp_path) == tmp_path / "AGENTS.md"
    assert hosts.resolve_instruction_path("opencode", tmp_path) == tmp_path / "AGENTS.md"
    assert hosts.resolve_instruction_path("claude", tmp_path) == tmp_path / "CLAUDE.md"


def test_resolve_hermes_profile(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".hermes" / "profiles" / "iris").mkdir(parents=True)
    (home / ".hermes" / "profiles" / "sophie").mkdir(parents=True)
    (home / ".hermes" / "active_profile").write_text("sophie")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert hosts.active_profile() == "sophie"
    assert set(hosts.list_profiles()) == {"iris", "sophie"}
    assert hosts.resolve_instruction_path("hermes", tmp_path, profile="iris") == \
        home / ".hermes" / "profiles" / "iris" / "SOUL.md"
    # default profile = active
    assert hosts.resolve_instruction_path("hermes", tmp_path) == \
        home / ".hermes" / "profiles" / "sophie" / "SOUL.md"


def test_resolve_openclaw_workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    oc = home / ".openclaw"
    (oc / "workspace").mkdir(parents=True)
    import json
    (oc / "openclaw.json").write_text(json.dumps(
        {"agents": {"defaults": {"workspace": str(oc / "workspace")}}}))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert hosts.default_workspace() == str(oc / "workspace")
    ws = oc / "workspace"
    assert hosts.resolve_instruction_path("openclaw", tmp_path, workspace=str(ws)) == ws / "AGENTS.md"
