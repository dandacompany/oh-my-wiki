"""Uninstall must also remove the `omw` short-alias skill dir, not just oh-my-wiki —
otherwise the alias is orphaned after `omw uninstall`."""
from pathlib import Path

from scripts import agent_skills, uninstall


def test_detect_skills_finds_alias(tmp_path, monkeypatch):
    skills_dir = tmp_path / ".claude" / "skills"
    (skills_dir / "oh-my-wiki").mkdir(parents=True)
    (skills_dir / agent_skills._ALIAS_NAME).mkdir(parents=True)
    # point every agent at this one dir; hermes targets at an empty tree
    monkeypatch.setattr(agent_skills, "_SKILLS_DIR",
                        {k: skills_dir for k in agent_skills._SKILLS_DIR})
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda *a, **k: [])
    paths = {Path(s["path"]).name for s in uninstall._detect_skills()}
    assert "oh-my-wiki" in paths and agent_skills._ALIAS_NAME in paths


def test_apply_removes_alias_bundle(tmp_path):
    alias = tmp_path / ".claude" / "skills" / agent_skills._ALIAS_NAME
    alias.mkdir(parents=True)
    (alias / "SKILL.md").write_text("alias", encoding="utf-8")
    plan = {
        "hosts": [], "hooks": [],
        "skills": [{"agent": "claude", "path": str(alias)}],
        "home": {}, "pip_hint": "pip uninstall oh-my-wiki",
    }
    uninstall.apply(plan)
    assert not alias.exists()


def test_apply_does_not_remove_unrelated_dir(tmp_path):
    # safety guard: only oh-my-wiki / omw bundles are rmtree'd, never an arbitrary path
    other = tmp_path / ".claude" / "skills" / "some-other-skill"
    other.mkdir(parents=True)
    plan = {
        "hosts": [], "hooks": [],
        "skills": [{"agent": "claude", "path": str(other)}],
        "home": {}, "pip_hint": "x",
    }
    uninstall.apply(plan)
    assert other.exists()  # untouched — not one of ours
