"""GitHub star nudge — state transitions + suppression, hermetic (OMW_HOME=tmp)."""
from datetime import datetime, timedelta

import pytest

from scripts import star

_NOW = datetime(2026, 7, 9, 12, 0, 0)
_AFTER = _NOW + timedelta(days=star.GRACE_DAYS, seconds=1)


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path))
    monkeypatch.delenv("OMW_NO_STAR", raising=False)
    yield


def test_install_nudge_sets_first_seen_then_silent_until_grace():
    # first call: records first_seen, no nudge
    assert star.maybe_install_nudge(now=_NOW, is_tty=True) is None
    assert star.load_state()["first_seen"] is not None
    # before grace elapses: still silent
    assert star.maybe_install_nudge(now=_NOW + timedelta(days=1), is_tty=True) is None


def test_install_nudge_fires_once_after_grace():
    star.maybe_install_nudge(now=_NOW, is_tty=True)          # seed first_seen
    line = star.maybe_install_nudge(now=_AFTER, is_tty=True)  # grace elapsed
    assert line and star.REPO_URL in line
    assert star.load_state()["install_nudge_shown"] is True
    # never again
    assert star.maybe_install_nudge(now=_AFTER, is_tty=True) is None


def test_install_nudge_silent_when_not_tty():
    star.maybe_install_nudge(now=_NOW, is_tty=True)
    assert star.maybe_install_nudge(now=_AFTER, is_tty=False) is None


def test_update_nudge_tty_and_suppression(monkeypatch):
    assert star.maybe_update_nudge(now=_NOW, is_tty=True)         # shows
    assert star.maybe_update_nudge(now=_NOW, is_tty=False) is None  # non-tty silent
    monkeypatch.setenv("OMW_NO_STAR", "1")
    assert star.maybe_update_nudge(now=_NOW, is_tty=True) is None   # env off


def test_dismiss_silences_both():
    star.maybe_install_nudge(now=_NOW, is_tty=True)  # seed
    star.dismiss()
    assert star.load_state()["dismissed"] is True
    assert star.maybe_update_nudge(now=_NOW, is_tty=True) is None
    assert star.maybe_install_nudge(now=_AFTER, is_tty=True) is None


def test_config_nudge_false_suppresses(monkeypatch):
    from scripts import config
    config.set_config("star.nudge", False)
    assert star.suppressed() is True
    assert star.maybe_update_nudge(now=_NOW, is_tty=True) is None


def test_status_shape_and_nudge_line():
    st = star.status()
    assert set(st) >= {"first_seen", "install_nudge_shown", "dismissed", "suppressed", "repo"}
    assert st["repo"] == star.REPO_URL
    assert "\n" not in star.nudge_line() and star.REPO_URL in star.nudge_line()


def test_load_state_survives_corrupt_file(tmp_path):
    star.state_path().parent.mkdir(parents=True, exist_ok=True)
    star.state_path().write_text("{ not json", encoding="utf-8")
    assert star.load_state() == dict(star._DEFAULT_STATE)
