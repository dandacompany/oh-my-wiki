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
    text = (root / raw_rel).read_text(encoding="utf-8")
    from scripts import frontmatter
    meta, body = frontmatter.parse(text)
    assert meta["source_url"] == "https://example.com/good"
    assert body == "hello body"


def test_run_skips_url_already_present_in_raw(tmp_path, monkeypatch):
    from scripts import ingest

    db, root, vid = _vault(tmp_path)
    existing = ingest.save_raw(
        db, vault_id=vid, content="original", ext="md", title="Existing",
        date_str="2026-06-01", source_url="https://example.com/article",
    )
    inbox.add(db, vault_id=vid, url="https://example.com/article")

    def should_not_fetch(*args, **kwargs):
        raise AssertionError("dedup must happen before fetch")

    monkeypatch.setattr(inbox.fetch, "fetch_url", should_not_fetch)
    result = inbox.run(db, vault_id=vid, today="2026-06-02")

    assert result["fetched"] == []
    assert result["deduped"] == [{
        "url": "https://example.com/article", "raw_relpath": existing,
    }]
    assert len(list((root / "raw").glob("*.md"))) == 1
    item = inbox.list_items(db, vault_id=vid)[0]
    assert item["status"] == "fetched"
    assert item["raw_relpath"] == existing
