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


import os, sys as _sys, subprocess as _sp


def _run_cli(args, env):
    return _sp.run([_sys.executable, "-m", "scripts.omw_cli", *args], capture_output=True, text=True, env=env)


def test_setup_playwright_section_is_silent_when_present(monkeypatch):
    # When chromium is available, setup_playwright prints "이미 설치" and exits 0 (no install).
    monkeypatch.setattr(sw, "playwright_installed", lambda: True)
    rc = sw.setup_playwright(noninteractive=True)
    assert rc == 0


def test_cli_setup_playwright_known_section():
    env = dict(os.environ)
    # `omw setup playwright --noninteractive` must be a recognized section (rc 0), not argparse error (rc 2).
    r = _run_cli(["setup", "playwright", "--noninteractive"], env)
    assert r.returncode == 0, r.stderr


from pathlib import Path as _Path

REPO = _Path(__file__).resolve().parents[1]


def test_no_bare_pip_install_playwright_in_code_or_skill():
    for rel in ["scripts/setup_wizard.py", "commands/inbox.md"]:
        t = (REPO / rel).read_text(encoding="utf-8")
        assert "pip install playwright" not in t, f"{rel} still has the PEP668-broken hint"


def test_doctor_points_to_setup_playwright():
    t = (REPO / "scripts" / "setup_wizard.py").read_text(encoding="utf-8")
    assert "omw setup playwright" in t  # chromium-missing hint routes here
