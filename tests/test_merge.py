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
            "---\ntitle: A\ntype: concept\ntags: [x, y]\nrelations:\n  uses: [foo]\n---\n\n## Summary\n\nalpha body\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\ntags: [y, z]\nrelations:\n  uses: [bar]\n---\n\n## Summary\n\nbeta body\n"
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
    assert set(wmeta["relations"]["uses"]) == {"foo", "bar"}
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


def test_stage_refuses_third_page_slug_conflict(tmp_path, monkeypatch):
    """Guard: refuse if a THIRD page's slug equals the source slug."""
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": (
            "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\nalpha\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nbeta\n"
        ),
        # third page whose relpath-slug is also "a" — collision
        "wiki/entities/a.md": (
            "---\ntitle: A Entity\ntype: entity\n---\n\n## Summary\n\nentity a\n"
        ),
    })
    with pytest.raises(merge.MergeError, match="third page"):
        merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                    target_relpath="wiki/concepts/b.md")


def test_stage_missing_file(tmp_path, monkeypatch):
    """Guard: source relpath that does not exist raises FileNotFoundError."""
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nbeta\n"
        ),
    })
    with pytest.raises(FileNotFoundError):
        merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/nonexistent.md",
                    target_relpath="wiki/concepts/b.md")


# ---------------------------------------------------------------------------
# Task 5: merge.apply tests
# ---------------------------------------------------------------------------


def test_apply_writes_and_resolves(tmp_path, monkeypatch):
    from scripts import registry, frontmatter
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\nalpha\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nbeta\n",
        "wiki/concepts/ref.md": "---\ntitle: Ref\ntype: concept\n---\n\n## Summary\n\nsee [[a]]\n",
    })
    root = registry.get_vault_root(db, vid)
    res = merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                      target_relpath="wiki/concepts/b.md")
    out = merge.apply(db, vault_id=vid,
                      winner_proposal=res["winner_proposal"],
                      source_proposal=res["source_proposal"])
    assert out["status"] == "applied" and out["merged_into"] == "b"
    # proposals consumed; source is now a tombstone; winner has merged body
    assert not (root / "wiki/concepts/b.md.proposed.md").exists()
    smeta, _ = frontmatter.parse((root / "wiki/concepts/a.md").read_text())
    assert smeta["status"] == "merged"
    wmeta, wbody = frontmatter.parse((root / "wiki/concepts/b.md").read_text())
    assert "a" in wmeta["aliases"] and "Merged from [[a]]" in wbody
    # [[a]] in ref now resolves to the winner (b) via alias
    from scripts import links
    bl = links.backlinks(db, vid, "wiki/concepts/b.md")
    assert any(r["relpath"] == "wiki/concepts/ref.md" for r in bl)


def test_apply_missing_proposal_aborts(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nb\n",
    })
    with pytest.raises(merge.MergeError):
        merge.apply(db, vault_id=vid,
                    winner_proposal="wiki/concepts/b.md.proposed.md",  # not staged
                    source_proposal="wiki/concepts/a.md.proposed.md")


def test_cli_merge_stage(tmp_path, monkeypatch):
    from scripts import omw_cli, registry
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\nalpha body words here now\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nbeta body words here now\n",
    })
    root = registry.get_vault_root(db, vid)
    rc = omw_cli.main(["merge", "wiki/concepts/a.md", "wiki/concepts/b.md"])
    assert rc == 0
    assert (root / "wiki/concepts/b.md.proposed.md").exists()


def test_stage_proposals_invisible_to_reindex(tmp_path, monkeypatch):
    """C1: staged .proposed.md sidecars must not appear as notes after reindex."""
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": (
            "---\ntitle: A\ntype: concept\ntags: [x]\n---\n\n## Summary\n\nalpha body\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\ntags: [y]\n---\n\n## Summary\n\nbeta body\n"
        ),
    })
    merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                target_relpath="wiki/concepts/b.md")
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        rows = conn.execute(
            "SELECT relpath FROM notes WHERE vault_id = ?", (vid,)
        ).fetchall()
    finally:
        conn.close()
    relpaths = [r["relpath"] for r in rows]
    assert not any(rp.endswith(".proposed.md") for rp in relpaths), (
        f"Proposal sidecars leaked into notes table: {[rp for rp in relpaths if rp.endswith('.proposed.md')]}"
    )


def test_stage_proposals_invisible_to_lint(tmp_path, monkeypatch):
    """C1: staged .proposed.md sidecars must not appear in wiki_lint results."""
    from scripts import wiki_lint
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": (
            "---\ntitle: A\ntype: concept\ntags: [x]\n---\n\n## Summary\n\nalpha body words here\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\ntags: [y]\n---\n\n## Summary\n\nbeta body words here\n"
        ),
    })
    merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                target_relpath="wiki/concepts/b.md")
    report = wiki_lint.check(db, vault_id=vid)
    dup_slugs = [
        slug
        for pair in report.get("content_duplicate_candidates", [])
        for slug in (pair.get("slug_a", ""), pair.get("slug_b", ""))
    ]
    assert not any(s.endswith(".proposed") for s in dup_slugs), (
        f"Proposal sidecar leaked into lint content_duplicate_candidates: {dup_slugs}"
    )
    # Also assert no other lint key references a .proposed path
    import json
    report_str = json.dumps(report)
    assert ".proposed.md" not in report_str, (
        "A .proposed.md path appeared somewhere in the lint report"
    )


def test_cli_apply_multiple_proposals_errors(tmp_path, monkeypatch):
    """Fix 1: --apply must refuse when multiple staged proposals share the source slug."""
    from scripts import omw_cli, registry
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\nalpha body words here now\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nbeta body words here now\n",
    })
    root = registry.get_vault_root(db, vid)
    # Stage a normal merge: creates b.md.proposed.md (winner) + a.md.proposed.md (source tombstone)
    res = merge.stage(db, vault_id=vid,
                      source_relpath="wiki/concepts/a.md",
                      target_relpath="wiki/concepts/b.md")
    winner_proposal = res["winner_proposal"]
    # Inject a colliding proposal in a different subdirectory (same stripped-name slug "a")
    collider = root / "wiki/entities/a.md.proposed.md"
    collider.parent.mkdir(parents=True, exist_ok=True)
    collider.write_text(
        "---\ntitle: A Entity\nstatus: merged\nmerged_into: b\n---\n\n> Merged into [[b]].\n",
        encoding="utf-8",
    )
    # --apply must return rc=1 (ambiguous match) and leave the winner proposal untouched
    rc = omw_cli.main(["merge", "--apply", winner_proposal])
    assert rc == 1
    # Winner proposal must still exist (apply was NOT executed)
    assert (root / winner_proposal).exists()
