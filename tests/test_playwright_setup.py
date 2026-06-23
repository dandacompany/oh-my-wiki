import subprocess
import scripts.setup_wizard as sw
from scripts import platform_env


def test_never_silent_noninteractive(monkeypatch):
    monkeypatch.setattr(sw, "playwright_installed", lambda: False)
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["pip", "install", p])
    called = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: called.append(a))
    ok, msg = sw.install_playwright(assume_yes=False, interactive=False)
    assert ok is False and called == []
    assert "playwright" in msg


def test_happy_path_runs_two_commands(monkeypatch):
    monkeypatch.setattr(sw, "playwright_installed", lambda: False)
    monkeypatch.setattr(platform_env, "pip_install_argv", lambda p: ["pipx", "inject", "oh-my-wiki", p, "--include-apps"])
    runs = []
    monkeypatch.setattr(sw.subprocess, "run", lambda cmd, **k: runs.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    ok, msg = sw.install_playwright(assume_yes=True)
    assert ok is True
    assert runs[0] == ["pipx", "inject", "oh-my-wiki", "playwright", "--include-apps"]
    assert runs[1][1:] == ["-m", "playwright", "install", "--with-deps", "chromium"]  # runs[1][0] == sys.executable


def test_reuse_when_installed(monkeypatch):
    monkeypatch.setattr(sw, "playwright_installed", lambda: True)
    ran = []
    monkeypatch.setattr(sw.subprocess, "run", lambda *a, **k: ran.append(a))
    ok, msg = sw.install_playwright(assume_yes=True)
    assert ok is True and ran == []
