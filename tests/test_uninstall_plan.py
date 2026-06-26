from pathlib import Path

from scripts import uninstall


def _seed_host_file(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    (base / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\nuser stuff.\n\n"
        "<!-- omw-recall:start -->\n## omw wiki recall (managed)\n\nx\n<!-- omw-recall:end -->\n",
        encoding="utf-8")


def test_plan_detects_host_markers(tmp_path, monkeypatch):
    omw_home = tmp_path / ".omw"
    (omw_home / "vaults").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OMW_HOME", str(omw_home))
    base = tmp_path / "proj"
    _seed_host_file(base)
    p = uninstall.plan(base, hosts=["claude"])
    claude = [h for h in p["hosts"] if h["host"] == "claude"]
    assert claude and "omw-recall" in claude[0]["markers"]
    assert "pip" in p["pip_hint"]
    assert isinstance(p["home"], dict)


def test_plan_clean_base_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    # Redirect all skills dirs to empty tmp dirs so installed bundles don't bleed in
    from scripts import agent_skills
    empty_skills = tmp_path / "skills"
    empty_skills.mkdir()
    monkeypatch.setattr(agent_skills, "_SKILLS_DIR",
                        {k: empty_skills for k in agent_skills._SKILLS_DIR})
    monkeypatch.setattr(agent_skills, "hermes_profile_targets", lambda: [])
    base = tmp_path / "empty"
    base.mkdir()
    p = uninstall.plan(base, hosts=["claude"])
    assert p["hosts"] == []        # no markers anywhere
    assert p["skills"] == []


def test_plan_never_raises_on_garbage(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    base = tmp_path / "x"
    base.mkdir()
    (base / "CLAUDE.md").write_text("\x00 binary-ish \xff", encoding="latin-1")
    # must not raise
    p = uninstall.plan(base, hosts=["claude"])
    assert isinstance(p, dict)
