from scripts import uninstall


def _seed(tmp_path):
    base = tmp_path / "proj"
    base.mkdir()
    (base / "CLAUDE.md").write_text(
        "user top.\n\n<!-- omw-recall:start -->\n## managed\n\nx\n<!-- omw-recall:end -->\n\nuser bottom.\n",
        encoding="utf-8")
    skills = tmp_path / ".claude" / "skills" / "oh-my-wiki"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("bundle", encoding="utf-8")
    home = tmp_path / ".omw"
    (home / "vaults" / "v1").mkdir(parents=True)
    (home / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    (home / ".env").write_text("OMW_SERVE_TOKEN=x\n", encoding="utf-8")
    (home / "registry.db").write_text("db", encoding="utf-8")
    return base, skills, home


def _plan(base, skills, home, vault_path):
    return {
        "hosts": [{"host": "claude", "path": str(base / "CLAUDE.md"), "markers": ["omw-recall"]}],
        "hooks": [],
        "skills": [{"agent": "claude", "path": str(skills)}],
        "home": {"path": str(home), "exists": True, "config": True, "env": True,
                 "registry": True, "vaults": [{"name": "v1", "path": str(vault_path)}]},
        "pip_hint": "pip uninstall oh-my-wiki",
    }


def test_apply_tier1_strips_block_and_skill_keeps_home(tmp_path):
    base, skills, home = _seed(tmp_path)
    vault_path = home / "vaults" / "v1"
    res = uninstall.apply(_plan(base, skills, home, vault_path))
    # block stripped, user content kept
    md = (base / "CLAUDE.md").read_text(encoding="utf-8")
    assert "omw-recall" not in md and "user top." in md and "user bottom." in md
    # skill bundle gone
    assert not skills.exists()
    # home + vaults UNTOUCHED (no --purge/--vaults)
    assert (home / "config.yaml").exists()
    assert (home / "registry.db").exists()
    assert vault_path.exists()
    assert res["purged"] is None and res["vaults_deleted"] is None


def test_apply_purge_removes_config_registry_keeps_vaults(tmp_path):
    base, skills, home = _seed(tmp_path)
    vault_path = home / "vaults" / "v1"
    uninstall.apply(_plan(base, skills, home, vault_path), purge=True)
    assert not (home / "config.yaml").exists()
    assert not (home / ".env").exists()
    assert not (home / "registry.db").exists()
    assert vault_path.exists()   # vaults preserved under --purge


def test_apply_vaults_deletes_vault_content(tmp_path):
    base, skills, home = _seed(tmp_path)
    vault_path = home / "vaults" / "v1"
    res = uninstall.apply(_plan(base, skills, home, vault_path), vaults=True)
    assert not vault_path.exists()
    assert res["vaults_deleted"] == [{"name": "v1", "path": str(vault_path)}]


def test_apply_dry_run_mutates_nothing(tmp_path):
    base, skills, home = _seed(tmp_path)
    vault_path = home / "vaults" / "v1"
    before = (base / "CLAUDE.md").read_text(encoding="utf-8")
    res = uninstall.apply(_plan(base, skills, home, vault_path),
                          purge=True, vaults=True, dry_run=True)
    assert res["dry_run"] is True
    assert (base / "CLAUDE.md").read_text(encoding="utf-8") == before  # unchanged
    assert skills.exists()
    assert (home / "config.yaml").exists()
    assert vault_path.exists()
    # but the summary still reports what WOULD be removed
    assert res["blocks_removed"] and res["skills_removed"]
    assert res["purged"] is not None and res["vaults_deleted"]
