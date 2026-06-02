import io
import re

from scripts import banner


def test_version_is_semver_and_matches_plugin_json():
    v = banner.version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v), v
    import json, pathlib
    pj = json.loads((pathlib.Path(banner.__file__).resolve().parents[1]
                     / ".claude-plugin" / "plugin.json").read_text())
    assert v == pj["version"]


def test_version_plugin_json_fallback(monkeypatch):
    import importlib.metadata as m
    def boom(_name):
        raise m.PackageNotFoundError("oh-my-wiki")
    monkeypatch.setattr(m, "version", boom)
    v = banner.version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v)  # came from plugin.json


def test_banner_text_has_wordmark_footer_and_version():
    t = banner.banner_text()
    assert "|___/" in t                                   # figlet wordmark fragment
    assert "github.com/dandacompany/oh-my-wiki" in t
    assert "https://oh-my-wiki.com" in t
    assert "dante@dante-labs.com" in t
    assert "Dante Labs" in t
    assert banner.version() in t
    assert "\x1b[" not in t                               # no ANSI when color off (default)


def test_should_animate_guard_matrix(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self): return True
    class NoTTY(io.StringIO):
        def isatty(self): return False
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OMW_NO_BANNER", raising=False)
    assert banner.should_animate(TTY()) is True
    assert banner.should_animate(NoTTY()) is False
    for var in ("NO_COLOR", "CI", "OMW_NO_BANNER"):
        monkeypatch.setenv(var, "1")
        assert banner.should_animate(TTY()) is False
        monkeypatch.delenv(var)


def test_render_static_no_escape_no_sleep():
    calls = []
    out = io.StringIO()
    banner.render(animate=False, stream=out, sleep=lambda *_: calls.append(1))
    s = out.getvalue()
    assert "|___/" in s and banner.version() in s
    assert "\r" not in s and "\x1b[" not in s
    assert calls == []                                    # no animation → no sleep


def test_render_animated_uses_spinner_frames_bounded():
    frames = []
    out = io.StringIO()
    banner.render(animate=True, stream=out, sleep=lambda *_: frames.append(1), color=True)
    s = out.getvalue()
    assert any(ch in s for ch in banner.SPINNER)          # spinner frames emitted
    assert "\r" in s                                      # single-line redraw
    assert 0 < len(frames) < 200                          # bounded, no infinite loop


import subprocess, sys as _sys, os
from pathlib import Path

_REPO = str(Path(banner.__file__).resolve().parents[1])


def _run(args, **env):
    e = {**os.environ, **env}
    return subprocess.run([_sys.executable, "-m", "scripts.omw_cli", *args],
                          capture_output=True, text=True, cwd=_REPO, env=e)


def test_cli_bare_shows_banner_and_help():
    r = _run([])
    assert r.returncode == 0
    assert "|___/" in r.stdout            # banner
    assert "usage: omw" in r.stdout       # help


def test_cli_help_shows_banner():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "|___/" in r.stdout and "usage: omw" in r.stdout


def test_cli_help_piped_has_no_ansi():
    # captured (non-tty) → banner static, no escape codes
    r = _run(["--help"])
    assert "\x1b[" not in r.stdout


def test_setup_run_all_emits_banner(monkeypatch, capsys, tmp_path):
    from scripts import setup_wizard
    # stub every section to no-op so run_all just exercises the banner + flow
    for name in ("run", "setup_search", "setup_serve", "setup_tts",
                 "setup_personas", "setup_import", "setup_viewer"):
        monkeypatch.setattr(setup_wizard, name, lambda **k: 0)
    setup_wizard.run_all(noninteractive=True, base_dir=tmp_path)
    out = capsys.readouterr().out
    assert "|___/" in out      # wordmark printed at the top of the wizard


def test_install_sh_contains_wordmark():
    sh = (Path(_REPO) / "bin" / "install.sh").read_text(encoding="utf-8")
    assert "|___/" in sh          # the wordmark is embedded for the bash banner
    assert "oh-my-wiki.com" in sh  # footer info present in the installer banner


def test_render_suppressed_by_omw_no_banner(monkeypatch):
    monkeypatch.setenv("OMW_NO_BANNER", "1")
    out = io.StringIO()
    banner.render(animate=False, stream=out, sleep=lambda *_: None)
    assert out.getvalue() == ""   # fully suppressed, any surface


def test_cli_help_omw_no_banner_suppresses():
    r = _run(["--help"], OMW_NO_BANNER="1")
    assert "|___/" not in r.stdout    # banner suppressed
    assert "usage: omw" in r.stdout   # help text still shown


def test_render_survives_broken_pipe():
    class BadStream:
        def write(self, *a): raise BrokenPipeError()
        def flush(self): raise BrokenPipeError()
        def isatty(self): return False
    # must not raise
    banner.render(animate=False, stream=BadStream(), sleep=lambda *_: None)
    banner.render(animate=True, stream=BadStream(), sleep=lambda *_: None)
