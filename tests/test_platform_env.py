from pathlib import Path
from scripts import platform_env as pe


def test_is_wsl_via_env(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert pe.is_wsl() is True


def test_is_wsl_via_proc_version(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(pe, "_proc_version", lambda: "Linux ... microsoft-standard-WSL2 ...")
    assert pe.is_wsl() is True


def test_is_wsl_false_on_plain_linux(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(pe, "_proc_version", lambda: "Linux version 6.1.0 (gcc) #1 SMP")
    assert pe.is_wsl() is False


def test_windows_user_profile_via_cmd(monkeypatch):
    monkeypatch.setattr(pe, "_userprofile_windows", lambda: r"C:\Users\dante")
    assert pe.windows_user_profile() == Path("/mnt/c/Users/dante")


def test_to_unc_path(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    got = pe.to_unc_path("/home/dante/.omw/vaults/x")
    assert got == r"\\wsl.localhost\Ubuntu\home\dante\.omw\vaults\x"
