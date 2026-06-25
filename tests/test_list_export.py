from scripts import registry, reindex


def test_reindex_persists_type_and_status(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/c.md": "---\ntitle: C\ntype: concept\nstatus: processed\n---\n\n## Summary\n\nx\n",
        "wiki/concepts/n.md": "---\ntitle: N\n---\n\n## Summary\n\ny\n",
    })
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        c = conn.execute("SELECT type, status FROM notes WHERE relpath = ?",
                         ("wiki/concepts/c.md",)).fetchone()
        n = conn.execute("SELECT type, status FROM notes WHERE relpath = ?",
                         ("wiki/concepts/n.md",)).fetchone()
    finally:
        conn.close()
    assert c["type"] == "concept" and c["status"] == "processed"
    assert n["type"] is None and n["status"] is None


def test_list_faceted(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\nstatus: processed\ntags: [ml]\n---\n\n## Summary\n\na\n",
        "wiki/entities/b.md": "---\ntitle: B\ntype: entity\nstatus: superseded\ntags: [ml, x]\n---\n\n## Summary\n\nb\n",
    })
    def rels(rows):
        return {r["relpath"] for r in rows}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, type_="concept")) == {"wiki/concepts/a.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, status="superseded")) == {"wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="ml")) == {"wiki/concepts/a.md", "wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="x")) == {"wiki/entities/b.md"}
    assert rels(registry.list_notes_faceted(db, vault_id=vid, tag="ml", type_="entity")) == {"wiki/entities/b.md"}


def test_export_slice_and_manifest(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import exporter, reindex, links
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\nsee [[b]] and [[gone]]\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\nb body\n",
        "wiki/concepts/gone.md": "---\ntitle: Gone\ntype: concept\ntags: [other]\n---\n\n## Summary\n\ng\n",
    })
    reindex.full(db, vault_id=vid)
    links.resolve(db, vid)
    out = tmp_path / "slice"
    res = exporter.export(db, vault_id=vid, out_dir=str(out), tag="pub")
    assert set(res["exported"]) == {"wiki/concepts/a.md", "wiki/concepts/b.md"}
    assert (out / "wiki/concepts/a.md").exists() and (out / "wiki/concepts/b.md").exists()
    assert not (out / "wiki/concepts/gone.md").exists()
    manifest = (out / "EXPORT_MANIFEST.md").read_text()
    assert "gone" in manifest                              # dangling listed
    assert "see [[b]] and [[gone]]" in (out / "wiki/concepts/a.md").read_text()  # body preserved verbatim
    assert any(d["slug"] == "gone" for d in res["dangling"])


def test_export_refuses_inside_vault(tmp_path, monkeypatch):
    import pytest
    from tests.conftest import make_vault_with_pages
    from scripts import exporter, registry
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\na\n",
    })
    root = registry.get_vault_root(db, vid)
    with pytest.raises(exporter.ExportError):
        exporter.export(db, vault_id=vid, out_dir=str(root / "sub"))


def test_cli_export_resolves_first(tmp_path, monkeypatch):
    """omw export must reindex+resolve links before exporting so the dangling
    manifest is accurate.  Without a prior reindex/resolve, every link has
    dst_note_id=NULL and all outbound links show as dangling (including in-slice
    ones).  This test verifies that calling main(["export", ...]) directly — with
    NO manual reindex/resolve beforehand — still produces a correct manifest
    where [[b]] (in-slice) is NOT dangling and [[gone]] (out-of-slice) IS."""
    from tests.conftest import make_vault_with_pages
    from scripts import omw_cli
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": (
            "---\ntitle: A\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\n"
            "see [[b]] and [[gone]]\n"
        ),
        "wiki/concepts/b.md": (
            "---\ntitle: B\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\nb body\n"
        ),
        "wiki/concepts/gone.md": (
            "---\ntitle: Gone\ntype: concept\ntags: [other]\n---\n\n## Summary\n\ng\n"
        ),
    })
    # Intentionally NO reindex.full / links.resolve here — _cmd_export must do it
    out_dir = tmp_path / "slice"
    rc = omw_cli.main(["export", "--tag", "pub", "--out", str(out_dir)])
    assert rc == 0
    manifest = (out_dir / "EXPORT_MANIFEST.md").read_text()
    # [[gone]] is out-of-slice → must appear as dangling
    assert "[[gone]]" in manifest
    # [[b]] is in-slice → must NOT appear in the dangling section
    # The manifest format is "## Dangling links ... \n- `page` → [[slug]]"
    dangling_section = manifest.split("## Dangling")[1] if "## Dangling" in manifest else ""
    assert "[[b]]" not in dangling_section


def test_export_zip(tmp_path, monkeypatch):
    import zipfile
    from tests.conftest import make_vault_with_pages
    from scripts import exporter
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\na\n",
    })
    zp = tmp_path / "slice.zip"
    exporter.export(db, vault_id=vid, zip_path=str(zp), tag="pub")
    assert zp.exists()
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
    assert "wiki/concepts/a.md" in names and "EXPORT_MANIFEST.md" in names


def test_export_refuses_nonempty_dir_without_force(tmp_path, monkeypatch):
    import pytest
    from tests.conftest import make_vault_with_pages
    from scripts import exporter
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\ntags: [pub]\n---\n\n## Summary\n\na\n",
    })
    out = tmp_path / "slice"
    out.mkdir()
    (out / "stale.txt").write_text("old")
    with pytest.raises(exporter.ExportError):
        exporter.export(db, vault_id=vid, out_dir=str(out), tag="pub")
    # force=True succeeds
    res = exporter.export(db, vault_id=vid, out_dir=str(out), tag="pub", force=True)
    assert res["status"] if "status" in res else res["out"]
