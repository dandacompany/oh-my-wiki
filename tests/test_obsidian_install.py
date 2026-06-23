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
