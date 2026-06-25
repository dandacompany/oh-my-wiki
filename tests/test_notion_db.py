from scripts import import_source, registry


def test_child_database_rows_imported(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/index.md": "# I\n"})
    root = registry.get_vault_root(db, vid)

    # Fake the Notion API: root page has one child_database block; the DB query
    # returns two row pages (paginated: page 1 has_more, page 2 done).
    pages = {
        "ROOT": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "Root"}]}}},
        "R1": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "Row One"}]}}},
        "R2": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "Row Two"}]}}},
    }
    children = {
        "ROOT": [{"type": "child_database", "id": "DB1"}],
        "R1": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "body one"}]}}],
        "R2": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "body two"}]}}],
    }

    def fake_get(url, *, headers=None):
        pid = url.rstrip("/").split("/")[-1]
        return pages[pid]

    def fake_post(url, *, headers, json_body):
        if json_body.get("start_cursor") == "C2":
            return {"results": [{"id": "R2"}], "has_more": False, "next_cursor": None}
        return {"results": [{"id": "R1"}], "has_more": True, "next_cursor": "C2"}

    monkeypatch.setattr(import_source, "_http_get", fake_get)
    monkeypatch.setattr(import_source, "_http_post", fake_post)
    monkeypatch.setattr(import_source, "_notion_children",
                        lambda token, bid: children.get(bid, []))

    res = import_source.import_notion(db, vault_id=vid, token="t", root_id="ROOT")
    imported = set(res["imported"])
    assert any(p.endswith("/row-one.md") for p in imported)
    assert any(p.endswith("/row-two.md") for p in imported)
    assert (root / "raw/import/notion/row-one.md").exists()


def test_notion_import_cycle_terminates(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import import_source
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/index.md": "# I\n"})
    pages = {"A": {"properties": {"Name": {"type": "title", "title": [{"plain_text": "A"}]}}}}
    # A's children contain a child_page pointing back to A (cycle)
    children = {"A": [{"type": "child_page", "id": "A"}]}
    monkeypatch.setattr(import_source, "_http_get", lambda url, *, headers=None: pages["A"])
    monkeypatch.setattr(import_source, "_notion_children", lambda t, b: children.get(b, []))
    res = import_source.import_notion(db, vault_id=vid, token="t", root_id="A")
    # A imported exactly once despite the self-cycle
    assert sum(1 for p in res["imported"] if p.endswith("/a.md")) == 1
