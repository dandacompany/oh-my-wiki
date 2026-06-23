import subprocess

import scripts.viewers.obsidian as ob


def test_installed_darwin_app(monkeypatch):
    monkeypatch.setattr(ob.sys, "platform", "darwin")
    monkeypatch.setattr(ob.shutil, "which", lambda _: None)
    monkeypatch.setattr(ob.Path, "exists", lambda self: str(self) == "/Applications/Obsidian.app")
    assert ob.obsidian_installed() is True


def test_installed_linux_which(monkeypatch):
    monkeypatch.setattr(ob.sys, "platform", "linux")
    monkeypatch.setattr(ob.shutil, "which", lambda n: "/usr/bin/obsidian" if n == "obsidian" else None)
    assert ob.obsidian_installed() is True


def test_not_installed_linux(monkeypatch):
    monkeypatch.setattr(ob.sys, "platform", "linux")
    monkeypatch.setattr(ob.shutil, "which", lambda _: None)
    monkeypatch.setattr(ob.Path, "exists", lambda self: False)
    assert ob.obsidian_installed() is False


def test_install_never_silent_noninteractive(monkeypatch):
    monkeypatch.setattr(ob, "obsidian_installed", lambda: False)
    called = []
    monkeypatch.setattr(ob.subprocess, "run", lambda *a, **k: called.append(a))
    ok, msg = ob.install_obsidian(assume_yes=False, interactive=False)
    assert ok is False
    assert called == []                      # nothing ran
    assert "obsidian.md" in msg              # manual link shown


def test_install_darwin_brew(monkeypatch):
    monkeypatch.setattr(ob, "obsidian_installed", lambda: False)
    monkeypatch.setattr(ob.sys, "platform", "darwin")
    monkeypatch.setattr(ob.shutil, "which", lambda n: "/opt/homebrew/bin/brew" if n == "brew" else None)
    ran = []
    monkeypatch.setattr(ob.subprocess, "run", lambda cmd, **k: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    ok, msg = ob.install_obsidian(assume_yes=True)
    assert ok is True
    assert ran == [["brew", "install", "--cask", "obsidian"]]


def test_install_wsl_deb(monkeypatch):
    monkeypatch.setattr(ob, "obsidian_installed", lambda: False)
    monkeypatch.setattr(ob.sys, "platform", "linux")
    monkeypatch.setattr(ob, "_is_debian_like", lambda: True)
    monkeypatch.setattr(ob, "_latest_deb_url", lambda: "https://x/obsidian.deb")
    monkeypatch.setattr(ob, "_download", lambda url, dest: dest.write_bytes(b"x"))
    ran = []
    monkeypatch.setattr(ob.subprocess, "run", lambda cmd, **k: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    ok, msg = ob.install_obsidian(assume_yes=True)
    assert ok is True
    assert ran and ran[0][:4] == ["sudo", "apt", "install", "-y"]
