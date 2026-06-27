import sys

from scripts import kiwi_install


def test_kiwi_available_returns_bool():
    assert isinstance(kiwi_install.kiwi_available(), bool)


def test_ensure_kiwi_no_autoinstall_without_consent(monkeypatch):
    # not available + non-interactive + no assume_yes → must NOT install, return False
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    called = {"pip": False}
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.__setitem__("pip", True))
    assert kiwi_install.ensure_kiwi(interactive=True) is False
    assert called["pip"] is False


def test_ensure_kiwi_returns_true_when_already_available(monkeypatch):
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: True)
    assert kiwi_install.ensure_kiwi() is True


def test_ensure_kiwi_never_raises(monkeypatch):
    monkeypatch.setattr(kiwi_install, "kiwi_available", lambda: False)
    import subprocess
    def boom(*a, **k):
        raise RuntimeError("pip exploded")
    monkeypatch.setattr(subprocess, "run", boom)
    # assume_yes bypasses the prompt; pip raises → ensure_kiwi must swallow and return False
    assert kiwi_install.ensure_kiwi(assume_yes=True) is False
