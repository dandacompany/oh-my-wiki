# tests/test_inbox_crud.py
from pathlib import Path

from scripts import inbox, registry


def _db(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    registry.add_vault(db, name="v", path=Path(tmp_path / "v"), type_="markdown", mode="wiki")
    return db


def test_add_inserts_queued_row_and_normalizes(tmp_path):
    db = _db(tmp_path)
    vid = registry.list_vaults(db)[0]["id"]
    row = inbox.add(db, vault_id=vid, url="https://youtu.be/dQw4w9WgXcQ?t=5")
    assert row["status"] == "queued"
    assert row["normalized_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_add_dedupes_on_normalized_url(tmp_path):
    db = _db(tmp_path)
    vid = registry.list_vaults(db)[0]["id"]
    inbox.add(db, vault_id=vid, url="https://EXAMPLE.com/a?utm_source=x")
    dup = inbox.add(db, vault_id=vid, url="https://example.com/a")  # same after normalize
    assert dup["deduped"] is True
    assert len(inbox.list_items(db, vault_id=vid)) == 1


def test_list_and_remove_and_clear(tmp_path):
    db = _db(tmp_path)
    vid = registry.list_vaults(db)[0]["id"]
    inbox.add(db, vault_id=vid, url="https://example.com/a")
    inbox.add(db, vault_id=vid, url="https://example.com/b")
    assert len(inbox.list_items(db, vault_id=vid)) == 2
    inbox.remove(db, vault_id=vid, url="https://example.com/a")
    assert len(inbox.list_items(db, vault_id=vid)) == 1
    inbox.clear(db, vault_id=vid)
    assert inbox.list_items(db, vault_id=vid) == []
