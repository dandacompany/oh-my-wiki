import shutil
import scripts.agent_skills as ask


def test_detect_agents_filters_by_which(monkeypatch):
    present = {"codex", "hermes"}
    monkeypatch.setattr(shutil, "which", lambda b: f"/bin/{b}" if b in present else None)
    assert ask.detect_agents() == ["codex", "hermes"]


def test_copy_bundle_includes_skill_md_excludes_tests(tmp_path):
    repo = tmp_path / "repo"
    (repo / "commands").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "SKILL.md").write_text("---\nname: oh-my-wiki\n---\n")
    (repo / "commands" / "ingest.md").write_text("x")
    (repo / "tests" / "t.py").write_text("y")
    dest_dir = tmp_path / "skills"
    out = ask._copy_bundle(dest_dir, repo_root=repo)
    assert (out / "SKILL.md").is_file()
    assert (out / "commands" / "ingest.md").is_file()
    assert not (out / "tests").exists()


def test_copy_bundle_excludes_dev_cruft_and_nested_claude(tmp_path):
    """The bundle must not ship .claude (nests a duplicate skill tree → scan
    storms), dev caches, or the per-user runtime data/ (leaks registry.db)."""
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills" / "oh-my-wiki").mkdir(parents=True)
    (repo / ".claude" / "skills" / "oh-my-wiki" / "SKILL.md").write_text("nested")
    (repo / ".superpowers").mkdir()
    (repo / ".ruff_cache").mkdir()
    (repo / "data").mkdir()
    (repo / "data" / "registry.db").write_text("USERDB")
    (repo / "commands").mkdir()
    (repo / "commands" / "ingest.md").write_text("x")
    (repo / "SKILL.md").write_text("---\nname: oh-my-wiki\n---\n")
    out = ask._copy_bundle(tmp_path / "skills", repo_root=repo)
    assert (out / "SKILL.md").is_file()
    assert (out / "commands" / "ingest.md").is_file()   # real content kept
    for gone in (".claude", ".superpowers", ".ruff_cache", "data"):
        assert not (out / gone).exists(), f"{gone} must be excluded from the bundle"


def test_copy_bundle_replaces_dangling_symlink(tmp_path):
    """A stale symlink left by a prior install (target moved away) must not abort
    the copy with FileExistsError — it should be cleared and replaced."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("---\nname: oh-my-wiki\n---\n")
    skills = tmp_path / "skills"
    skills.mkdir()
    # Dangling symlink at <skills>/oh-my-wiki pointing at a now-missing target.
    (skills / "oh-my-wiki").symlink_to(tmp_path / "gone")
    out = ask._copy_bundle(skills, repo_root=repo)
    assert not out.is_symlink()
    assert (out / "SKILL.md").is_file()


def test_install_alias_replaces_dangling_symlink(tmp_path):
    """The short-alias install must survive a stale symlink at <skills>/omw."""
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "omw").symlink_to(tmp_path / "gone")  # dangling
    dest = ask.install_alias_into_dir(skills)
    assert not dest.is_symlink()
    assert (dest / "SKILL.md").is_file()


def test_copy_bundle_includes_backends_excludes_dev(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backends").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "SKILL.md").write_text("x")
    (repo / "backends" / "codex.json").write_text("{}")
    (repo / "tests" / "t.py").write_text("y")
    out = ask._copy_bundle(tmp_path / "skills", repo_root=repo)
    assert (out / "backends" / "codex.json").is_file()  # runtime model catalog must ship
    assert (out / "SKILL.md").is_file()
    assert not (out / "tests").exists()
    assert not (out / "docs").exists()


def test_install_hermes_uses_copy(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setitem(ask._SKILLS_DIR, "hermes", tmp_path / "h" / "skills")
    r = ask.install("hermes", repo_root=repo)
    assert r["ok"] and r["method"] == "copy"
    assert (tmp_path / "h" / "skills" / "oh-my-wiki" / "SKILL.md").is_file()


def test_install_codex_prefers_skills_cli(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setattr(shutil, "which", lambda b: "/bin/skills" if b == "skills" else None)
    seen = {}
    class P:
        returncode = 0
    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return P()
    monkeypatch.setattr(ask.subprocess, "run", fake_run)
    r = ask.install("codex", repo_root=repo)
    assert r["ok"] and r["method"] == "skills-cli"
    assert seen["cmd"][:2] == ["skills", "add"]
    assert "-a" in seen["cmd"] and "codex" in seen["cmd"]


def test_install_codex_falls_back_to_copy_on_failure(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setitem(ask._SKILLS_DIR, "codex", tmp_path / "c" / "skills")
    monkeypatch.setattr(shutil, "which", lambda b: "/bin/skills" if b == "skills" else None)
    class P:
        returncode = 1
    monkeypatch.setattr(ask.subprocess, "run", lambda cmd, **k: P())
    r = ask.install("codex", repo_root=repo)
    assert r["ok"] and r["method"] == "copy"
    assert (tmp_path / "c" / "skills" / "oh-my-wiki" / "SKILL.md").is_file()


def test_install_many_isolates_failures(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    def fake_install(agent, **k):
        if agent == "codex":
            raise RuntimeError("boom")
        return {"agent": agent, "ok": True, "method": "copy"}
    monkeypatch.setattr(ask, "install", fake_install)
    out = ask.install_many(["hermes", "codex"], repo_root=repo)
    assert out[0]["ok"] is True
    assert out[1]["ok"] is False and "boom" in out[1]["detail"]


def test_install_many_forwards_use_skills_cli(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "SKILL.md").write_text("x")
    monkeypatch.setitem(ask._SKILLS_DIR, "codex", tmp_path / "c" / "skills")
    monkeypatch.setattr(shutil, "which", lambda b: "/bin/skills" if b == "skills" else None)
    def boom(*a, **k):
        raise AssertionError("skills CLI must not run when use_skills_cli=False")
    monkeypatch.setattr(ask.subprocess, "run", boom)
    out = ask.install_many(["codex"], repo_root=repo, use_skills_cli=False)
    assert out[0]["ok"] and out[0]["method"] == "copy"


def test_detect_includes_opencode_openclaw(monkeypatch):
    from scripts import agent_skills
    monkeypatch.setattr(agent_skills.shutil, "which",
                        lambda b: f"/usr/bin/{b}")  # all bins present
    detected = agent_skills.detect_agents()
    assert "opencode" in detected and "openclaw" in detected
    assert detected.index("opencode") >= 0 and detected.index("openclaw") >= 0


def test_skill_dirs_for_new_agents():
    from scripts import agent_skills
    from pathlib import Path
    assert agent_skills._SKILLS_DIR["opencode"] == Path.home() / ".config" / "opencode" / "skills"
    # openclaw reads the shared personal catalog (~/.agents/skills), NOT ~/.openclaw/skills
    # (paths under ~/.openclaw/skills resolve outside openclaw's configured skill root and
    # are skipped). Install there so the skill is actually discoverable.
    assert agent_skills._SKILLS_DIR["openclaw"] == Path.home() / ".agents" / "skills"


def _make_hermes(tmp_path, profiles=(), installed=()):
    """Build a fake ~/.hermes tree. `installed` = profile names (or 'main')
    that already have an oh-my-wiki skill dir."""
    home = tmp_path / ".hermes"
    (home / "skills").mkdir(parents=True)
    for p in profiles:
        (home / "profiles" / p / "skills").mkdir(parents=True)
    for name in installed:
        skills = (home / "skills") if name == "main" else (home / "profiles" / name / "skills")
        (skills / "oh-my-wiki").mkdir(parents=True, exist_ok=True)
    return home


def test_hermes_targets_main_plus_profiles_sorted(tmp_path):
    home = _make_hermes(tmp_path, profiles=["sophie", "iris", "mark"])
    targets = ask.hermes_profile_targets(hermes_home=home)
    assert [t["name"] for t in targets] == ["main", "iris", "mark", "sophie"]
    assert targets[0]["skills_dir"] == home / "skills"
    assert targets[1]["skills_dir"] == home / "profiles" / "iris" / "skills"


def test_hermes_targets_installed_flag(tmp_path):
    home = _make_hermes(tmp_path, profiles=["iris", "mark"], installed=["main", "mark"])
    targets = {t["name"]: t["installed"] for t in ask.hermes_profile_targets(hermes_home=home)}
    assert targets == {"main": True, "iris": False, "mark": True}


def test_hermes_targets_degrades_to_main_when_absent(tmp_path):
    # no ~/.hermes at all
    targets = ask.hermes_profile_targets(hermes_home=tmp_path / ".hermes")
    assert [t["name"] for t in targets] == ["main"]
    assert targets[0]["installed"] is False


def test_install_into_dir_copies_bundle(tmp_path):
    dest = tmp_path / "skills"
    dest.mkdir()
    result = ask.install_into_dir(dest)
    assert result["ok"] is True
    assert result["method"] == "copy"
    assert (dest / "oh-my-wiki" / "SKILL.md").exists()
    assert result["dest"] == str(dest / "oh-my-wiki")


def test_install_into_dir_oserror_returns_error_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(ask, "_copy_bundle", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    result = ask.install_into_dir(tmp_path / "skills")
    assert result == {"ok": False, "method": "copy", "dest": None, "detail": "boom"}
