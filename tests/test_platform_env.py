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


def test_windows_user_profile_returns_none_on_oserror(monkeypatch):
    """windows_user_profile() must return None (not raise) when /mnt/c/Users scan raises OSError."""
    monkeypatch.setattr(pe, "_userprofile_windows", lambda: None)

    class _FakePath:
        def is_dir(self):
            return True

        def iterdir(self):
            raise OSError("permission denied")

    monkeypatch.setattr(pe, "_WIN_USERS", _FakePath())
    result = pe.windows_user_profile()
    assert result is None


def test_install_context_pipx(monkeypatch):
    monkeypatch.setattr(pe, "_prefix", lambda: "/home/d/.local/share/pipx/venvs/oh-my-wiki")
    monkeypatch.setattr(pe, "_base_prefix", lambda: "/usr")
    assert pe.omw_install_context() == "pipx"


def test_install_context_venv(monkeypatch):
    monkeypatch.setattr(pe, "_prefix", lambda: "/home/d/proj/.venv")
    monkeypatch.setattr(pe, "_base_prefix", lambda: "/usr")
    assert pe.omw_install_context() == "venv"


def test_install_context_system(monkeypatch):
    monkeypatch.setattr(pe, "_prefix", lambda: "/usr")
    monkeypatch.setattr(pe, "_base_prefix", lambda: "/usr")
    assert pe.omw_install_context() == "system"


def test_pip_install_argv_pipx(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "pipx")
    assert pe.pip_install_argv("playwright") == ["pipx", "inject", "oh-my-wiki", "playwright", "--include-apps"]


def test_pip_install_argv_venv(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "venv")
    monkeypatch.setattr(pe, "_executable", lambda: "/v/bin/python")
    assert pe.pip_install_argv("playwright") == ["/v/bin/python", "-m", "pip", "install", "playwright"]


def test_pip_install_argv_system_pep668(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "system")
    monkeypatch.setattr(pe, "pep668_managed", lambda: True)
    monkeypatch.setattr(pe, "_executable", lambda: "/usr/bin/python3")
    assert pe.pip_install_argv("playwright") == ["/usr/bin/python3", "-m", "pip", "install", "--break-system-packages", "playwright"]


def test_pip_install_argv_system_plain(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "system")
    monkeypatch.setattr(pe, "pep668_managed", lambda: False)
    monkeypatch.setattr(pe, "_executable", lambda: "/usr/bin/python3")
    assert pe.pip_install_argv("playwright") == ["/usr/bin/python3", "-m", "pip", "install", "playwright"]
