from scripts import wiki_lint


def test_jaccard_edges():
    assert wiki_lint._jaccard(set(), set()) == 0.0
    s = {("a", "b", "c")}
    assert wiki_lint._jaccard(s, s) == 1.0


def test_detects_content_overlap(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    long_body = (
        "## Summary\n\n" + " ".join(f"word{i}" for i in range(60)) + "\n"
    )
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": f"---\ntitle: A\ntype: concept\n---\n\n{long_body}",
        "wiki/concepts/b.md": f"---\ntitle: B\ntype: concept\n---\n\n{long_body}",
    })
    rep = wiki_lint.check(db, vault_id=vid)
    cands = rep["content_duplicate_candidates"]
    assert len(cands) == 1
    c = cands[0]
    assert {c["slug_a"], c["slug_b"]} == {"a", "b"}
    assert c["similarity"] >= 0.55
    assert c["suggested"] == f"omw merge {c['slug_a']} {c['slug_b']}"


def test_short_stubs_not_flagged(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\nshort identical stub\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\nshort identical stub\n",
    })
    rep = wiki_lint.check(db, vault_id=vid)
    assert rep["content_duplicate_candidates"] == []


def test_distinct_content_not_flagged(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    a = "## Summary\n\n" + " ".join(f"alpha{i}" for i in range(60)) + "\n"
    b = "## Summary\n\n" + " ".join(f"beta{i}" for i in range(60)) + "\n"
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": f"---\ntitle: A\ntype: concept\n---\n\n{a}",
        "wiki/concepts/b.md": f"---\ntitle: B\ntype: concept\n---\n\n{b}",
    })
    rep = wiki_lint.check(db, vault_id=vid)
    assert rep["content_duplicate_candidates"] == []
