# tests/test_setup_viewer_wsl.py
from pathlib import Path
import scripts.setup_wizard as sw


def test_setup_viewer_wsl_prints_two_paths(tmp_path, monkeypatch, capsys):
    # Active vault on a WSL linux path.
    vault = tmp_path / ".omw" / "vaults" / "mens-fashion-kr"
    vault.mkdir(parents=True)
    monkeypatch.setattr(sw.registry, "get_active", lambda db: {"name": "mens-fashion-kr", "path": str(vault)})
    monkeypatch.setattr(sw, "registry_path", lambda: tmp_path / "registry.db")
    monkeypatch.setattr(sw.config, "set_config", lambda *a, **k: None)
    # Pretend WSL + Obsidian missing; never actually install or register to real paths.
    from scripts import platform_env
    monkeypatch.setattr(platform_env, "is_wsl", lambda: True)
    monkeypatch.setattr(platform_env, "windows_user_profile", lambda: Path("/mnt/c/Users/dante"))
    import scripts.viewers.obsidian as ob
    monkeypatch.setattr(ob, "obsidian_installed", lambda: False)
    monkeypatch.setattr(ob, "install_obsidian", lambda **k: (False, "건너뜀"))
    monkeypatch.setattr(ob, "register_vault_windows", lambda *a, **k: True)

    rc = sw.setup_viewer(viewer="obsidian", noninteractive=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "wsl.localhost" in out                      # EISDIR trap warned
    assert "--location" in out and "/mnt/c/Users/dante" in out  # path ② guidance with real win user
