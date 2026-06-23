import scripts.setup_wizard as sw
from scripts import platform_env


def test_ensure_present_no_install(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: True)
    called = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: called.append(a))
    assert sw.ensure_wizard_ui() is True
    assert called == []


def test_ensure_non_tty_no_install(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)
    monkeypatch.delenv("OMW_BOOTSTRAP_YES", raising=False)
    monkeypatch.setattr(sw.sys.stdin, "isatty", lambda: False)
    called = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: called.append(a))
    assert sw.ensure_wizard_ui() is False
    assert called == []


def test_ensure_confirmed_install_runs_pip(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)  # stays missing in test env
    monkeypatch.setenv("OMW_BOOTSTRAP_YES", "1")
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["pipx", "inject", "oh-my-wiki", p])
    runs = []
    import subprocess as _sp
    monkeypatch.setattr(sw.subprocess, "run", lambda cmd, **k: runs.append(cmd) or _sp.CompletedProcess(cmd, 0))
    inval = []
    monkeypatch.setattr(sw.importlib, "invalidate_caches", lambda: inval.append(True))
    sw.ensure_wizard_ui()
    assert runs == [["pipx", "inject", "oh-my-wiki", "questionary"]]
    assert inval == [True]


def test_ensure_one_attempt_per_process(monkeypatch):
    monkeypatch.setattr(sw, "_WIZARD_UI_TRIED", False)
    monkeypatch.setattr(sw, "_questionary_available", lambda: False)
    monkeypatch.setenv("OMW_BOOTSTRAP_YES", "1")
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["x"])
    runs = []
    import subprocess as _sp
    monkeypatch.setattr(sw.subprocess, "run", lambda cmd, **k: runs.append(cmd) or _sp.CompletedProcess(cmd, 0))
    monkeypatch.setattr(sw.importlib, "invalidate_caches", lambda: None)
    sw.ensure_wizard_ui()
    sw.ensure_wizard_ui()
    assert len(runs) == 1  # second call short-circuits on the flag
