import json
from pathlib import Path
import scripts.viewers.obsidian as ob


def test_windows_vault_path_mnt_c():
    assert ob.windows_vault_path(Path("/mnt/c/Users/dante/omw-vaults/x")) == r"C:\Users\dante\omw-vaults\x"


def test_windows_vault_path_wsl_fs(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert ob.windows_vault_path(Path("/home/dante/.omw/vaults/x")) == r"\\wsl.localhost\Ubuntu\home\dante\.omw\vaults\x"


def test_register_vault_windows_writes_win_path(tmp_path):
    cp = tmp_path / "obsidian.json"
    ok = ob.register_vault_windows(Path("/mnt/c/Users/dante/omw-vaults/x"), config_path=cp)
    assert ok is True
    data = json.loads(cp.read_text())
    paths = [v["path"] for v in data["vaults"].values()]
    assert r"C:\Users\dante\omw-vaults\x" in paths


def test_register_vault_windows_idempotent(tmp_path):
    cp = tmp_path / "obsidian.json"
    root = Path("/mnt/c/Users/dante/omw-vaults/x")
    assert ob.register_vault_windows(root, config_path=cp) is True
    assert ob.register_vault_windows(root, config_path=cp) is False  # already present
