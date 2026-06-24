from scripts import registry


def test_links_table_exists_after_init_db(tmp_db):
    registry.init_db(tmp_db)
    conn = registry.connect(tmp_db)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='links'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_init_db_idempotent_with_links(tmp_db):
    registry.init_db(tmp_db)
    registry.init_db(tmp_db)  # must not raise (IF NOT EXISTS)
    conn = registry.connect(tmp_db)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(links)")}
    finally:
        conn.close()
    assert cols == {"id", "vault_id", "src_note_id", "dst_slug",
                    "dst_note_id", "link_type", "position"}


from scripts import links


def test_extract_wikilink_simple():
    assert links.extract_links("see [[attention]] here") == [("attention", "wikilink", 0)]


def test_extract_wikilink_alias_and_heading():
    assert links.extract_links("[[attn|Attention]] and [[topic#sec]]") == [
        ("attn", "wikilink", 0),
        ("topic", "wikilink", 1),
    ]


def test_extract_markdown_internal_link():
    assert links.extract_links("[x](concepts/attn.md)") == [("attn", "markdown", 0)]


def test_extract_ignores_external_and_fragment_and_non_md():
    body = "[a](https://e.com) [b](mailto:x@y.z) [c](#sec) [d](img.png)"
    assert links.extract_links(body) == []


def test_extract_preserves_document_order_across_kinds():
    body = "[md](a.md) then [[wiki]] then [md2](b.md)"
    assert links.extract_links(body) == [
        ("a", "markdown", 0),
        ("wiki", "wikilink", 1),
        ("b", "markdown", 2),
    ]


def test_extract_skips_empty_targets():
    assert links.extract_links("[[ ]] and [x]()") == []


import pytest


@pytest.fixture
def vault(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "v"
    vroot.mkdir()
    row = registry.add_vault(
        tmp_db, name="v", path=str(vroot), type_="markdown", mode="wiki"
    )
    return tmp_db, row["id"]


def _add_note(db, vault_id, relpath, body=""):
    return registry.upsert_note(
        db, vault_id=vault_id, relpath=relpath, layer="wiki",
        title=relpath, summary=None, mtime=0.0, size_bytes=len(body), tags=[],
    )


def _link_rows(db, vault_id):
    conn = registry.connect(db)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT src_note_id, dst_slug, dst_note_id, link_type, position "
            "FROM links WHERE vault_id = ? ORDER BY src_note_id, position",
            (vault_id,),
        )]
    finally:
        conn.close()


def test_replace_links_inserts_unresolved(vault):
    db, vid = vault
    nid = _add_note(db, vid, "wiki/a.md", "[[b]] and [x](c.md)")
    links.replace_links(db, vault_id=vid, src_note_id=nid, body="[[b]] and [x](c.md)")
    rows = _link_rows(db, vid)
    assert [(r["dst_slug"], r["link_type"], r["position"]) for r in rows] == [
        ("b", "wikilink", 0), ("c", "markdown", 1)
    ]
    assert all(r["dst_note_id"] is None for r in rows)  # not resolved yet


def test_replace_links_is_idempotent_replace(vault):
    db, vid = vault
    nid = _add_note(db, vid, "wiki/a.md")
    links.replace_links(db, vault_id=vid, src_note_id=nid, body="[[b]]")
    links.replace_links(db, vault_id=vid, src_note_id=nid, body="[[c]]")  # replaces
    rows = _link_rows(db, vid)
    assert [r["dst_slug"] for r in rows] == ["c"]


def test_resolve_sets_dst_note_id_for_unique_match(vault):
    db, vid = vault
    a = _add_note(db, vid, "wiki/a.md", "[[b]] [[missing]]")
    b = _add_note(db, vid, "wiki/b.md")
    links.replace_links(db, vault_id=vid, src_note_id=a, body="[[b]] [[missing]]")
    links.resolve(db, vid)
    rows = {r["dst_slug"]: r["dst_note_id"] for r in _link_rows(db, vid)}
    assert rows["b"] == b
    assert rows["missing"] is None


def test_resolve_leaves_ambiguous_slug_unresolved(vault):
    db, vid = vault
    a = _add_note(db, vid, "wiki/a.md", "[[dup]]")
    _add_note(db, vid, "wiki/x/dup.md")
    _add_note(db, vid, "wiki/y/dup.md")  # same basename slug 'dup'
    links.replace_links(db, vault_id=vid, src_note_id=a, body="[[dup]]")
    links.resolve(db, vid)
    rows = {r["dst_slug"]: r["dst_note_id"] for r in _link_rows(db, vid)}
    assert rows["dup"] is None  # ambiguous -> unresolved


def test_resolve_repairs_after_target_added(vault):
    db, vid = vault
    a = _add_note(db, vid, "wiki/a.md", "[[late]]")
    links.replace_links(db, vault_id=vid, src_note_id=a, body="[[late]]")
    links.resolve(db, vid)
    assert _link_rows(db, vid)[0]["dst_note_id"] is None
    late = _add_note(db, vid, "wiki/late.md")
    links.resolve(db, vid)
    assert _link_rows(db, vid)[0]["dst_note_id"] == late


@pytest.fixture
def linked_vault(vault):
    """a -> b (resolved), a -> ghost (broken); b has no outbound; c is an orphan."""
    db, vid = vault
    a = _add_note(db, vid, "wiki/a.md", "[[b]] [[ghost]]")
    b = _add_note(db, vid, "wiki/b.md")
    c = _add_note(db, vid, "wiki/c.md")  # orphan (nothing links to it)
    _add_note(db, vid, "wiki/index.md")  # meta — must be excluded from orphans
    links.replace_links(db, vault_id=vid, src_note_id=a, body="[[b]] [[ghost]]")
    links.resolve(db, vid)
    return db, vid, {"a": a, "b": b, "c": c}


def test_backlinks(linked_vault):
    db, vid, ids = linked_vault
    back = links.backlinks(db, vid, "wiki/b.md")
    assert [r["relpath"] for r in back] == ["wiki/a.md"]
    assert links.backlinks(db, vid, "wiki/a.md") == []


def test_outbound(linked_vault):
    db, vid, ids = linked_vault
    out = links.outbound(db, vid, "wiki/a.md")
    assert [(r["dst_slug"], bool(r["resolved"])) for r in out] == [("b", True), ("ghost", False)]


def test_orphans_excludes_meta_and_linked(linked_vault):
    db, vid, ids = linked_vault
    orphans = {r["relpath"] for r in links.orphans(db, vid)}
    assert "wiki/c.md" in orphans       # nothing links to c
    assert "wiki/a.md" in orphans       # nothing links to a either
    assert "wiki/b.md" not in orphans   # a links to b
    assert "wiki/index.md" not in orphans  # meta excluded


def test_broken_links(linked_vault):
    db, vid, ids = linked_vault
    broken = links.broken_links(db, vid)
    assert [(r["src_relpath"], r["dst_slug"]) for r in broken] == [("wiki/a.md", "ghost")]


def test_graph(linked_vault):
    db, vid, ids = linked_vault
    edges = links.graph(db, vid)
    by_slug = {r["dst_slug"]: r for r in edges}
    assert by_slug["b"]["dst_relpath"] == "wiki/b.md" and by_slug["b"]["resolved"]
    assert by_slug["ghost"]["dst_relpath"] is None and not by_slug["ghost"]["resolved"]


from scripts import reindex


def _write(vroot, relpath, body):
    p = vroot / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntitle: " + relpath + "\ntype: concept\ntags: []\n---\n\n" + body,
        encoding="utf-8",
    )


def test_reindex_full_populates_and_resolves_links(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "wv"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(
        tmp_db, name="wv", path=str(vroot), type_="markdown", mode="wiki"
    )
    vid = row["id"]
    _write(vroot, "wiki/a.md", "links to [[b]] and [[ghost]]")
    _write(vroot, "wiki/b.md", "no outbound")
    reindex.full(tmp_db, vault_id=vid)
    assert [r["relpath"] for r in links.backlinks(tmp_db, vid, "wiki/b.md")] == ["wiki/a.md"]
    assert [r["dst_slug"] for r in links.broken_links(tmp_db, vid)] == ["ghost"]


def test_reindex_incremental_repairs_broken_link(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "wv2"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(
        tmp_db, name="wv2", path=str(vroot), type_="markdown", mode="wiki"
    )
    vid = row["id"]
    _write(vroot, "wiki/a.md", "points at [[late]]")
    reindex.full(tmp_db, vault_id=vid)
    assert [r["dst_slug"] for r in links.broken_links(tmp_db, vid)] == ["late"]
    _write(vroot, "wiki/late.md", "now exists")
    reindex.incremental(tmp_db, vault_id=vid)
    assert links.broken_links(tmp_db, vid) == []


def test_index_drift_reports_missing_and_dangling(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "iv"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="iv", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    _write(vroot, "wiki/index.md", "- [A](a.md)\n- [Ghost](ghost.md)")
    _write(vroot, "wiki/a.md", "page a")
    _write(vroot, "wiki/b.md", "page b not in index")
    reindex.full(tmp_db, vault_id=vid)
    drift = links.index_drift(tmp_db, vid)
    assert [n["relpath"] for n in drift["missing_from_index"]] == ["wiki/b.md"]
    assert [d["dst_slug"] for d in drift["dangling_in_index"]] == ["ghost"]


def test_index_drift_absent_index_lists_all_pages(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "iv2"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="iv2", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    _write(vroot, "wiki/a.md", "page a")
    reindex.full(tmp_db, vault_id=vid)
    drift = links.index_drift(tmp_db, vid)
    assert {n["relpath"] for n in drift["missing_from_index"]} == {"wiki/a.md"}
    assert drift["dangling_in_index"] == []


def test_extract_relations_dict():
    meta = {"relations": {"contradicts": ["old-claim"], "uses": ["helper"],
                          "supersedes": ["v1"]}}
    out = links.extract_relations(meta)
    kinds = {(slug, rel) for slug, rel, _pos in out}
    assert ("old-claim", "contradicts") in kinds
    assert ("helper", "uses") in kinds
    assert ("v1", "supersedes") in kinds


def test_extract_relations_scalar_and_missing():
    assert links.extract_relations({}) == []
    assert links.extract_relations({"relations": None}) == []
    assert links.extract_relations({"relations": "nope"}) == []
    out = links.extract_relations({"relations": {"contradicts": "solo"}})
    assert [(s, r) for s, r, _ in out] == [("solo", "contradicts")]
    assert links.extract_relations({"relations": {"bogus": ["x"]}}) == []


def test_replace_links_inserts_relations_from_meta(vault):
    db, vid = vault
    nid = _add_note(db, vid, "wiki/a.md")
    links.replace_links(db, vault_id=vid, src_note_id=nid,
                        body="see [[b]]", meta={"relations": {"contradicts": ["c"]}})
    rows = _link_rows(db, vid)
    by_type = {(r["dst_slug"], r["link_type"]) for r in rows}
    assert ("b", "wikilink") in by_type
    assert ("c", "contradicts") in by_type


def test_reindex_resolves_relations(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "rv"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="rv", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n"
        "relations:\n  contradicts: [b]\n---\n\nbody", encoding="utf-8")
    (vroot / "wiki" / "b.md").write_text(
        "---\ntitle: b\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    reindex.full(tmp_db, vault_id=vid)
    rows = _link_rows(tmp_db, vid)
    contr = [r for r in rows if r["link_type"] == "contradicts"]
    assert len(contr) == 1
    assert contr[0]["dst_note_id"] is not None  # resolved to b


def test_relations_query(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "qv"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="qv", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n"
        "relations:\n  contradicts: [b]\n  uses: [c]\n---\n\nbody", encoding="utf-8")
    (vroot / "wiki" / "b.md").write_text(
        "---\ntitle: b\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    reindex.full(tmp_db, vault_id=vid)
    allrel = links.relations(tmp_db, vid)
    assert {r["relation"] for r in allrel} == {"contradicts", "uses"}
    contr = links.relations(tmp_db, vid, relation="contradicts")
    assert len(contr) == 1
    assert contr[0]["src_relpath"] == "wiki/a.md"
    assert contr[0]["dst_relpath"] == "wiki/b.md"
    assert contr[0]["resolved"]


def test_extract_inline_relations_parses_keys():
    body = "supersedes:: [[old]]\nuses:: concept-x\nnote:: not a relation\n"
    rels = links.extract_inline_relations(body)
    assert ("old", "supersedes", 0) in rels or ("old", "supersedes") in {(s, r) for s, r, _ in rels}
    assert ("concept-x", "uses") in {(s, r) for s, r, _ in rels}
    assert all(r != "note" for _, r, _ in rels)  # non-relation key ignored


def test_reindex_picks_up_inline_relation(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = tmp_path / "r.db"
    registry.init_db(db)
    root = tmp_path / "v"
    (root / "wiki" / "concepts").mkdir(parents=True)
    v = registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    vid = v["id"]
    (root / "wiki" / "concepts" / "old.md").write_text(
        "---\ntitle: Old\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\n## Summary\nx\n", encoding="utf-8")
    (root / "wiki" / "concepts" / "new.md").write_text(
        "---\ntitle: New\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\n## Summary\ncontradicts:: [[old]]\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    edges = links.relations(db, vault_id=vid, relation="contradicts")
    pairs = {(e["src_relpath"], e["dst_relpath"]) for e in edges}
    assert ("wiki/concepts/new.md", "wiki/concepts/old.md") in pairs


def test_resolve_prefers_alias_owner(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import links
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        # winner declares alias 'old' and is linked to via [[old]]
        "wiki/concepts/winner.md": (
            "---\ntitle: Winner\ntype: concept\naliases: [old]\n---\n\n## Summary\n\nw\n"
        ),
        "wiki/concepts/ref.md": (
            "---\ntitle: Ref\ntype: concept\n---\n\n## Summary\n\nsee [[old]]\n"
        ),
    })
    links.resolve(db, vid)
    bl = links.backlinks(db, vid, "wiki/concepts/winner.md")
    assert any(r["relpath"] == "wiki/concepts/ref.md" for r in bl)


def test_resolve_alias_wins_over_relpath(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import links
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        # a tombstone keeps slug 'dup'; winner aliases 'dup' -> [[dup]] must hit winner
        "wiki/concepts/dup.md": (
            "---\ntitle: Dup\ntype: concept\nstatus: merged\nmerged_into: winner\n---\n\n> Merged into [[winner]].\n"
        ),
        "wiki/concepts/winner.md": (
            "---\ntitle: Winner\ntype: concept\naliases: [dup]\n---\n\n## Summary\n\nw\n"
        ),
        "wiki/concepts/ref.md": (
            "---\ntitle: Ref\ntype: concept\n---\n\n## Summary\n\nsee [[dup]]\n"
        ),
    })
    links.resolve(db, vid)
    bl = links.backlinks(db, vid, "wiki/concepts/winner.md")
    assert any(r["relpath"] == "wiki/concepts/ref.md" for r in bl)
