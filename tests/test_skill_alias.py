"""The `omw` short-alias skill — a sibling skill dir whose name is `omw`, installed
alongside the canonical `oh-my-wiki` skill so `/omw` (Claude) and `$omw` (Codex)
resolve. No native alias frontmatter key exists; the short invocation requires a
real skill dir named `omw`. The alias forwards to oh-my-wiki (single source of rules).
"""
import shutil
from pathlib import Path

import yaml

import scripts.agent_skills as ask

REPO = Path(__file__).resolve().parents[1]


def _frontmatter(text: str) -> dict:
    assert text.startswith("---")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


# ── the alias writer ─────────────────────────────────────────────────────────

def test_install_alias_writes_omw_skill(tmp_path):
    dest = ask.install_alias_into_dir(tmp_path)
    skill = Path(dest) / "SKILL.md"
    assert skill.is_file()
    assert _frontmatter(skill.read_text(encoding="utf-8"))["name"] == "omw"


def test_alias_frontmatter_has_hint_and_forwarding(tmp_path):
    text = (Path(ask.install_alias_into_dir(tmp_path)) / "SKILL.md").read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert "argument-hint" in fm and fm["argument-hint"]  # subcommand/arg hint present
    desc = fm["description"].lower()
    # short-alias trigger tokens so $omw / /omw and auto-activation both fire
    assert "omw" in desc and "alias" in desc
    # body forwards to the canonical skill rather than duplicating its rules
    assert "oh-my-wiki" in text


def test_install_alias_is_idempotent(tmp_path):
    ask.install_alias_into_dir(tmp_path)
    ask.install_alias_into_dir(tmp_path)
    skills = list((tmp_path / "omw").glob("SKILL.md"))
    assert len(skills) == 1


# ── alias rides along with every install path ────────────────────────────────

def test_install_into_dir_also_installs_alias(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    dest = tmp_path / "skills"
    dest.mkdir()
    ask.install_into_dir(dest, repo_root=repo)
    assert (dest / "oh-my-wiki" / "SKILL.md").is_file()
    assert (dest / "omw" / "SKILL.md").is_file()


def test_install_copy_agent_installs_alias(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setitem(ask._SKILLS_DIR, "hermes", tmp_path / "h" / "skills")
    r = ask.install("hermes", repo_root=repo)
    assert r["ok"]
    assert (tmp_path / "h" / "skills" / "omw" / "SKILL.md").is_file()
    assert r.get("alias_dest")  # additive key surfaces the alias location


def test_install_skills_cli_agent_still_installs_alias(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setitem(ask._SKILLS_DIR, "codex", tmp_path / "c" / "skills")
    monkeypatch.setattr(shutil, "which", lambda b: "/bin/skills" if b == "skills" else None)
    class P:
        returncode = 0
        stdout = ""
    monkeypatch.setattr(ask.subprocess, "run", lambda cmd, **k: P())
    r = ask.install("codex", repo_root=repo, use_skills_cli=True)
    assert r["ok"] and r["method"] == "skills-cli"
    # even when the main skill went via skills-cli, the alias lands in the agent's skills dir
    assert (tmp_path / "c" / "skills" / "omw" / "SKILL.md").is_file()


# ── canonical skill also advertises the argument hint ────────────────────────

def test_canonical_skill_md_has_argument_hint():
    fm = _frontmatter((REPO / "SKILL.md").read_text(encoding="utf-8"))
    assert "argument-hint" in fm and fm["argument-hint"]
