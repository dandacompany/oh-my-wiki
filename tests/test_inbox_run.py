# tests/test_inbox_run.py
from scripts import inbox, registry


def _vault(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "raw").mkdir(parents=True)
    (root / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    vid = registry.list_vaults(db)[0]["id"]
    return db, root, vid


def test_run_fetches_saves_raw_and_marks_fetched(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path)
    inbox.add(db, vault_id=vid, url="https://example.com/good")
    inbox.add(db, vault_id=vid, url="https://example.com/bad")

    def fake_fetch(url, *, html_backend="auto"):
        if url.endswith("/bad"):
            from scripts.fetch_errors import FetchError
            raise FetchError("boom")
        return {"text": "hello body", "title": "Good Page",
                "content_type": "text/html", "backend": "urllib", "source_url": url}

    monkeypatch.setattr(inbox.fetch, "fetch_url", fake_fetch)
    result = inbox.run(db, vault_id=vid, today="2026-06-02")

    assert len(result["fetched"]) == 1
    assert len(result["failed"]) == 1
    items = {i["url"]: i for i in inbox.list_items(db, vault_id=vid)}
    assert items["https://example.com/good"]["status"] == "fetched"
    assert items["https://example.com/good"]["raw_relpath"].startswith("raw/")
    assert items["https://example.com/bad"]["status"] == "failed"
    assert "boom" in items["https://example.com/bad"]["error"]
    raw_rel = items["https://example.com/good"]["raw_relpath"]
    assert (root / raw_rel).read_text(encoding="utf-8") == "hello body"
