"""Tests for setup_personas host-picker (Task 4: convention choices + scoped sub-prompts)."""
from pathlib import Path
from scripts import setup_wizard


def test_setup_personas_hermes_profile_noninteractive(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".hermes" / "profiles" / "iris").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = setup_wizard.setup_personas(enabled=["wiki-librarian"], main="wiki-librarian",
                                     hosts=["hermes"], profile="iris",
                                     noninteractive=True, base_dir=str(tmp_path))
    assert rc == 0
    assert (home / ".hermes" / "profiles" / "iris" / "SOUL.md").exists()


def test_setup_personas_hermes_multi_profiles(tmp_path, monkeypatch):
    """`profiles=[...]` fans out: every selected hermes profile gets a SOUL.md."""
    home = tmp_path / "home"
    for name in ("iris", "mark", "mia"):
        (home / ".hermes" / "profiles" / name).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = setup_wizard.setup_personas(enabled=["wiki-librarian"], main="wiki-librarian",
                                     hosts=["hermes"], profiles=["iris", "mark"],
                                     noninteractive=True, base_dir=str(tmp_path))
    assert rc == 0
    assert (home / ".hermes" / "profiles" / "iris" / "SOUL.md").exists()
    assert (home / ".hermes" / "profiles" / "mark" / "SOUL.md").exists()
    # a profile that was NOT selected stays untouched
    assert not (home / ".hermes" / "profiles" / "mia" / "SOUL.md").exists()


def test_setup_personas_legacy_single_profile_still_works(tmp_path, monkeypatch):
    """Back-compat: the legacy single `profile=` arg is normalized into the list."""
    home = tmp_path / "home"
    (home / ".hermes" / "profiles" / "iris").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = setup_wizard.setup_personas(enabled=["wiki-librarian"], main="wiki-librarian",
                                     hosts=["hermes"], profile="iris",
                                     noninteractive=True, base_dir=str(tmp_path))
    assert rc == 0
    assert (home / ".hermes" / "profiles" / "iris" / "SOUL.md").exists()


def test_setup_personas_unresolvable_scoped_skips_cleanly(tmp_path, monkeypatch):
    """Non-interactive hermes host with no profile should skip cleanly (return 0, no SOUL.md)."""
    home = tmp_path / "home"
    home.mkdir(parents=True)
    # No ~/.hermes/active_profile and no profiles directory → hermes cannot resolve.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = setup_wizard.setup_personas(
        enabled=["wiki-librarian"], main="wiki-librarian",
        hosts=["hermes"], noninteractive=True,
        base_dir=str(tmp_path), profile=None,
    )
    assert rc == 0
    # No SOUL.md should have been written anywhere under tmp home.
    soul_files = list(home.rglob("SOUL.md"))
    assert soul_files == [], f"unexpected SOUL.md files: {soul_files}"


def test_setup_recall_merged_agents_written_once(tmp_path, monkeypatch):
    rc = setup_wizard.setup_recall(noninteractive=True, base_dir=str(tmp_path),
                                   hosts=["codex", "opencode"], mode="auto", strategy="fts")
    assert rc == 0
    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("<!-- omw-recall:start -->") == 1
