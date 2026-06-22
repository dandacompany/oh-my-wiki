"""Unit tests for the central path resolver."""
from pathlib import Path

from scripts import paths


def test_omw_home_defaults_to_dot_omw(monkeypatch):
    monkeypatch.delenv("OMW_HOME", raising=False)
    assert paths.omw_home() == Path.home() / ".omw"


def test_omw_home_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "custom"))
    assert paths.omw_home() == tmp_path / "custom"


def test_omw_home_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OMW_HOME", "")
    assert paths.omw_home() == Path.home() / ".omw"


def test_registry_path_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    assert paths.registry_path() == tmp_path / "registry.db"


def test_default_vault_root_uses_slug(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    assert paths.default_vault_root("My Notes") == tmp_path / "vaults" / "my-notes"


def test_project_vault_root_uses_cwd_and_slug(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert paths.project_vault_root("My Notes") == tmp_path / ".omw" / "my-notes"


def test_ensure_home_creates_vaults_dir_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / "h"))
    paths.ensure_home()
    paths.ensure_home()  # second call must not raise
    assert (tmp_path / "h" / "vaults").is_dir()


def test_legacy_candidates_include_skill_dir_and_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cands = paths.legacy_registry_candidates()
    assert cands[1] == tmp_path / "data" / "registry.db"
    assert cands[0] != cands[1]
    assert cands[0].parent.name == "data" and cands[0].name == "registry.db"


def test_resolve_vault_root_branches(monkeypatch, tmp_path):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    assert paths.resolve_vault_root("v", "global") == tmp_path / "vaults" / "v"
    monkeypatch.chdir(tmp_path)
    assert paths.resolve_vault_root("v", "project") == tmp_path / ".omw" / "v"
    assert paths.resolve_vault_root("v", "/abs/x") == Path("/abs/x")


def test_bundled_root_prefers_repo_root_in_checkout():
    root = paths.bundled_root()
    # in this dev checkout the repo root (with schemas/) is authoritative
    assert (root / "schemas").is_dir()
    assert paths.bundled_dir("personas") == root / "personas"


def test_bundled_root_falls_back_to_package_bundle(monkeypatch, tmp_path):
    # simulate an installed wheel: repo-root sentinel absent → use <scripts>/_bundle
    fake_scripts = tmp_path / "scripts"
    (fake_scripts / "_bundle").mkdir(parents=True)
    monkeypatch.setattr(paths, "_PKG_DIR", fake_scripts, raising=False)
    monkeypatch.setattr(paths, "_REPO_ROOT", tmp_path / "nonexistent_root", raising=False)
    paths._bundled_root_cache = None  # reset cache
    assert paths.bundled_root() == fake_scripts / "_bundle"
    paths._bundled_root_cache = None  # clean up for other tests
