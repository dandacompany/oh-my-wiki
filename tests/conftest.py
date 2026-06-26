from pathlib import Path

import pytest

from scripts import registry

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db(tmp_path):
    """Empty sqlite file in a tmp dir."""
    return tmp_path / "registry.db"


@pytest.fixture
def markdown_vault_path():
    return FIXTURES / "markdown-vault"


@pytest.fixture
def obsidian_vault_path():
    return FIXTURES / "obsidian-vault"


@pytest.fixture
def db_connect():
    return registry.connect


@pytest.fixture(autouse=True)
def _isolate_omw_home(monkeypatch, tmp_path):
    """Every test gets an isolated OMW_HOME so the real ~/.omw is never touched. Also
    isolate OMW_HOOK_HOME so host hook wiring (~/.claude, ~/.codex, ~/.gemini, ~/.hermes,
    ~/.config/opencode, ~/.openclaw) writes under tmp, never the real home."""
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw-test"))
    monkeypatch.setenv("OMW_HOOK_HOME", str(tmp_path / ".home-test"))


def make_vault_with_pages(tmp_path, monkeypatch, pages: dict) -> tuple:
    """Create a registered, reindexed vault populated with the given pages.

    The registry DB is placed at OMW_HOME/registry.db so that omw_cli.main()
    calls (which resolve via registry_path() → OMW_HOME/registry.db) find it.

    Args:
        tmp_path: pytest tmp_path fixture value.
        monkeypatch: pytest monkeypatch fixture value.
        pages: mapping of relpath → markdown text (relpath is relative to vault root).

    Returns:
        (db_path, vault_id) — ready for search_index.query and omw_cli.main calls.
    """
    from scripts import registry, reindex

    omw_home = tmp_path / ".omw"
    (omw_home / "vaults").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OMW_HOME", str(omw_home))
    db = omw_home / "registry.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    root.mkdir(parents=True, exist_ok=True)
    v = registry.add_vault(db, name="default", path=root, type_="markdown", mode="wiki")
    registry.set_active(db, "default")

    for relpath, text in pages.items():
        abs_path = root / relpath
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(text, encoding="utf-8")

    reindex.full(db, vault_id=v["id"])
    return db, v["id"]
