from scripts import platform_env as pe


def test_upgrade_argv_pipx(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "pipx")
    assert pe.upgrade_argv("oh-my-wiki") == ["pipx", "upgrade", "oh-my-wiki"]


def test_upgrade_argv_venv(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "venv")
    monkeypatch.setattr(pe, "_executable", lambda: "/venv/bin/python")
    assert pe.upgrade_argv("oh-my-wiki") == ["/venv/bin/python", "-m", "pip", "install", "-U", "oh-my-wiki"]


def test_upgrade_argv_system_pep668(monkeypatch):
    monkeypatch.setattr(pe, "omw_install_context", lambda: "system")
    monkeypatch.setattr(pe, "pep668_managed", lambda: True)
    monkeypatch.setattr(pe, "_executable", lambda: "/usr/bin/python3")
    argv = pe.upgrade_argv("oh-my-wiki")
    assert "-U" in argv and "--break-system-packages" in argv
