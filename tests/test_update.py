from scripts import platform_env as pe, update


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


def test_latest_version_parses(monkeypatch):
    import json

    class _R:
        def read(self): return json.dumps({"info": {"version": "2.15.0"}}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda *a, **k: _R())
    assert update.latest_version("oh-my-wiki") == "2.15.0"


def test_latest_version_none_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("no net")
    monkeypatch.setattr(update.urllib.request, "urlopen", boom)
    assert update.latest_version("oh-my-wiki") is None


def test_run_check_only_no_subprocess(monkeypatch, capsys):
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: "2.15.0")
    called = {"n": 0}
    monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    rc = update.run(check_only=True, assume_yes=False, refresh=False)
    assert rc == 0 and called["n"] == 0


def test_run_assume_yes_upgrades(monkeypatch):
    # Pin current low + latest high so the "newer available" path fires regardless of
    # the installed package version (else a release bump can make latest == cur).
    monkeypatch.setattr(update.banner, "version", lambda: "0.0.0")
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: "9999.0.0")
    seen = {}

    class _CP:
        returncode = 0
    monkeypatch.setattr(update.subprocess, "run", lambda argv, **k: seen.update(argv=argv) or _CP())
    monkeypatch.setattr(update, "_refresh_blocks", lambda *a, **k: None)
    rc = update.run(check_only=False, assume_yes=True, refresh=False)
    assert rc == 0 and seen["argv"][0] in ("pipx", update.platform_env._executable())


def test_cli_update_check(monkeypatch, capsys):
    from scripts import omw_cli, update
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: "2.15.0")
    monkeypatch.setattr(update.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no upgrade on --check")))
    rc = omw_cli.main(["update", "--check"])
    assert rc == 0


def test_run_already_current_no_upgrade(monkeypatch):
    # When already on the latest version, never run the upgrade command — even with --yes.
    monkeypatch.setattr(update, "latest_version", lambda *a, **k: update.banner.version())
    monkeypatch.setattr(update.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no upgrade when current")))
    rc = update.run(check_only=False, assume_yes=True, refresh=True)
    assert rc == 0
