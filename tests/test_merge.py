import json

import pytest

from scripts import registry, reindex


def test_reindex_persists_aliases(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/winner.md": (
            "---\ntitle: Winner\ntype: concept\ntags: [t]\n"
            "aliases: [old-name, other-alias]\n---\n\n## Summary\n\nbody\n"
        ),
    })
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        row = conn.execute(
            "SELECT aliases FROM notes WHERE vault_id = ? AND relpath = ?",
            (vid, "wiki/concepts/winner.md"),
        ).fetchone()
    finally:
        conn.close()
    assert json.loads(row["aliases"]) == ["old-name", "other-alias"]


# ---------------------------------------------------------------------------
# Task 4: merge.stage tests
# ---------------------------------------------------------------------------

from scripts import merge  # noqa: E402


def _vault(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    return make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": (
            "---\ntitle: A\ntype: concept\ntags: [x, y]\nuses: [foo]\n---\n\n## Summary\n\nalpha body\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\ntags: [y, z]\nuses: [bar]\n---\n\n## Summary\n\nbeta body\n"
        ),
        "wiki/entities/e.md": (
            "---\ntitle: E\ntype: entity\n---\n\n## Summary\n\nentity\n"
        ),
    })


def test_stage_builds_winner_and_tombstone(tmp_path, monkeypatch):
    from scripts import frontmatter
    db, vid = _vault(tmp_path, monkeypatch)
    root = registry.get_vault_root(db, vid)
    before_target = (root / "wiki/concepts/b.md").read_text()
    res = merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                      target_relpath="wiki/concepts/b.md")
    assert res["status"] == "staged"
    # target + source files untouched
    assert (root / "wiki/concepts/b.md").read_text() == before_target
    # winner proposal: union frontmatter + merged body + alias
    wp = root / "wiki/concepts/b.md.proposed.md"
    sp = root / "wiki/concepts/a.md.proposed.md"
    assert wp.exists() and sp.exists()
    wmeta, wbody = frontmatter.parse(wp.read_text())
    assert set(wmeta["tags"]) == {"x", "y", "z"}
    assert set(wmeta["uses"]) == {"foo", "bar"}
    assert "a" in wmeta["aliases"]
    assert "## Merged from [[a]]" in wbody and "alpha body" in wbody
    # tombstone
    smeta, sbody = frontmatter.parse(sp.read_text())
    assert smeta["status"] == "merged" and smeta["merged_into"] == "b"
    assert "Merged into [[b]]" in sbody


def test_stage_type_guard(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    with pytest.raises(merge.MergeError):
        merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                    target_relpath="wiki/entities/e.md")
    # --force allows it
    res = merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                      target_relpath="wiki/entities/e.md", force=True)
    assert res["status"] == "staged"


def test_stage_refuses_remerge(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    root = registry.get_vault_root(db, vid)
    # make 'a' already a tombstone
    (root / "wiki/concepts/a.md").write_text(
        "---\ntitle: A\ntype: concept\nstatus: merged\nmerged_into: b\n---\n\n> Merged into [[b]].\n"
    )
    with pytest.raises(merge.MergeError):
        merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                    target_relpath="wiki/concepts/b.md")
