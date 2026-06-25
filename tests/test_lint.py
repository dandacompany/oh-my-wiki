from pathlib import Path
import pytest

from scripts import registry, reindex, lint, supersede, entity_link  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def broken_vault(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    import shutil
    dest = tmp_path / "broken"
    shutil.copytree(FIXTURES / "broken-vault", dest)
    vault = registry.add_vault(
        tmp_db, name="b", path=dest, type_="markdown", mode="memo"
    )
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, dest


def test_lint_reports_frontmatter_issues(broken_vault):
    db, vault, root = broken_vault
    report = lint.check(db, vault_id=vault["id"])
    relpaths = {item["relpath"] for item in report["frontmatter_issues"]}
    assert "bad-yaml.md" in relpaths
    assert "missing-title.md" in relpaths
    assert "tags-as-string.md" in relpaths
    assert "good.md" not in relpaths


def test_lint_detects_drift_missing_file(broken_vault):
    db, vault, root = broken_vault
    (root / "good.md").unlink()
    report = lint.check(db, vault_id=vault["id"])
    missing = {item["relpath"] for item in report["drift"]["missing_files"]}
    assert "good.md" in missing


def test_lint_detects_drift_orphan_row(broken_vault):
    db, vault, root = broken_vault
    registry.upsert_note(
        db, vault_id=vault["id"], relpath="ghost.md", layer="memo",
        title="ghost", summary=None, mtime=0.0, size_bytes=0, tags=[],
    )
    report = lint.check(db, vault_id=vault["id"])
    missing = {item["relpath"] for item in report["drift"]["missing_files"]}
    assert "ghost.md" in missing


def test_lint_reports_links_broken_and_orphans(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "lv"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(
        tmp_db, name="lv", path=str(vroot), type_="markdown", mode="wiki"
    )
    vid = row["id"]
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-30\ntags: []\n---\n\n[[ghost]]", encoding="utf-8"
    )
    (vroot / "wiki" / "b.md").write_text(
        "---\ntitle: b\ntype: concept\ndate: 2026-05-30\ntags: []\n---\n\norphan page", encoding="utf-8"
    )
    reindex.full(tmp_db, vault_id=vid)
    report = lint.check(tmp_db, vault_id=vid)
    assert report["frontmatter_issues"] == []   # fixture is otherwise clean
    assert [r["dst_slug"] for r in report["links"]["broken"]] == ["ghost"]
    orphan_paths = {r["relpath"] for r in report["links"]["orphans"]}
    assert {"wiki/a.md", "wiki/b.md"} <= orphan_paths


def test_lint_reports_index_drift(tmp_db, tmp_path):
    from scripts import registry, reindex, lint
    registry.init_db(tmp_db)
    vroot = tmp_path / "lid"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="lid", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    (vroot / "wiki" / "index.md").write_text("# Index\n\n- [A](a.md)\n", encoding="utf-8")
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    (vroot / "wiki" / "b.md").write_text(
        "---\ntitle: b\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    reindex.full(tmp_db, vault_id=vid)
    report = lint.check(tmp_db, vault_id=vid)
    assert "index_drift" in report["links"]
    assert [n["relpath"] for n in report["links"]["index_drift"]["missing_from_index"]] == ["wiki/b.md"]


def test_lint_hint_for_index_drift(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    vroot = tmp_path / "hd"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="hd", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    (vroot / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")  # links nothing
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    reindex.full(tmp_db, vault_id=vid)
    report = lint.check(tmp_db, vault_id=vid)
    assert any("Index drift" in h for h in report["auto_fix_hints"])


def test_lint_surfaces_contradictions(tmp_db, tmp_path):
    from scripts import registry, reindex, lint
    registry.init_db(tmp_db)
    vroot = tmp_path / "lc"
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name="lc", path=str(vroot), type_="markdown", mode="wiki")
    vid = row["id"]
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n"
        "relations:\n  contradicts: [b]\n---\n\nbody", encoding="utf-8")
    (vroot / "wiki" / "b.md").write_text(
        "---\ntitle: b\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    reindex.full(tmp_db, vault_id=vid)
    report = lint.check(tmp_db, vault_id=vid)
    assert [r["dst_slug"] for r in report["links"]["contradictions"]] == ["b"]
    assert any("contradiction" in h.lower() for h in report["auto_fix_hints"])


# ---------------------------------------------------------------------------
# Task 3: schema-sourced validation tests
# ---------------------------------------------------------------------------

def _make_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = tmp_path / "registry.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "wiki" / "entities").mkdir(parents=True)
    (root / "wiki").joinpath("index.md").write_text("# Index\n", encoding="utf-8")
    (root / "wiki").joinpath("log.md").write_text("# Log\n", encoding="utf-8")
    v = registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    return db, root, v["id"]


def test_lint_flags_missing_required_section(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    # entity page WITHOUT the required "## Summary" section
    (root / "wiki" / "entities" / "x.md").write_text(
        "---\ntitle: X\ndate: 2026-01-01\ntype: entity\ntags: [a]\n---\nbody\n",
        encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    issues = {i["issue"] for i in report["frontmatter_issues"]}
    assert "missing_section:## Summary" in issues


def test_lint_accepts_vault_override_type(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    (root / "schemas").mkdir()
    (root / "schemas" / "recipe.yml").write_text(
        "required_fields: [title, type]\nfield_types: {}\nrequired_sections: []\n",
        encoding="utf-8",
    )
    (root / "wiki" / "entities" / "r.md").write_text(
        "---\ntitle: R\ntype: recipe\n---\nbody\n", encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    issues = {(i["relpath"], i["issue"]) for i in report["frontmatter_issues"]}
    # 'recipe' is now a valid type (no invalid_type), required_fields satisfied
    assert ("wiki/entities/r.md", "invalid_type") not in issues


# ---------------------------------------------------------------------------
# Task 3 (F#4): status map, orphan exemption, superseded_unmarked
# ---------------------------------------------------------------------------

def test_lint_excludes_superseded_from_orphans(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    # an orphan wiki page (no inbound links), marked superseded
    (root / "wiki" / "entities" / "old.md").write_text(
        "---\ntitle: Old\ndate: 2026-01-01\ntype: entity\ntags: [a]\n"
        "status: superseded\nsuperseded_by: new\n---\n## Summary\nx\n",
        encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    orphan_relpaths = {o["relpath"] for o in report["links"]["orphans"]}
    assert "wiki/entities/old.md" not in orphan_relpaths


def test_lint_reports_superseded_unmarked(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    # B supersedes A via frontmatter relation; A is NOT yet marked
    (root / "wiki" / "entities" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\ntype: entity\ntags: [x]\n---\n## Summary\na\n",
        encoding="utf-8",
    )
    (root / "wiki" / "entities" / "b.md").write_text(
        "---\ntitle: B\ndate: 2026-01-01\ntype: entity\ntags: [x]\n"
        "relations: {supersedes: [a]}\n---\n## Summary\nb\n",
        encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    unmarked = {u["relpath"] for u in report["links"]["superseded_unmarked"]}
    assert "wiki/entities/a.md" in unmarked
    # after marking, it leaves the list
    supersede.mark_superseded(db, vault_id=vid, relpath="wiki/entities/a.md", by_slug="b")
    report2 = lint.check(db, vault_id=vid)
    unmarked2 = {u["relpath"] for u in report2["links"]["superseded_unmarked"]}
    assert "wiki/entities/a.md" not in unmarked2


def test_lint_reports_link_suggestions(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    (root / "wiki" / "entities" / "karpathy.md").write_text(
        "---\ntitle: Andrej Karpathy\ndate: 2026-01-01\ntype: entity\ntags: [p]\n---\n## Summary\nresearcher\n",
        encoding="utf-8")
    (root / "wiki" / "entities" / "tdd.md").write_text(
        "---\ntitle: TDD\ndate: 2026-01-01\ntype: concept\ntags: [m]\n---\n## Summary\nAndrej Karpathy wrote this.\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    pairs = {(s["src_relpath"], s["target_slug"]) for s in report["links"]["link_suggestions"]}
    assert ("wiki/entities/tdd.md", "karpathy") in pairs
    # applying the link clears it
    entity_link.apply_link(db, vault_id=vid, relpath="wiki/entities/tdd.md", target_slug="karpathy")
    report2 = lint.check(db, vault_id=vid)
    pairs2 = {(s["src_relpath"], s["target_slug"]) for s in report2["links"]["link_suggestions"]}
    assert ("wiki/entities/tdd.md", "karpathy") not in pairs2


# ---------------------------------------------------------------------------
# Task 4: lint report includes schema_load_errors for malformed schema files
# ---------------------------------------------------------------------------

def test_lint_surfaces_schema_load_errors(tmp_path, monkeypatch):
    db, root, vid = _make_vault(tmp_path, monkeypatch)
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "schemas" / "broken.yml").write_text("bad: : : yaml\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    report = lint.check(db, vault_id=vid)
    assert "schema_load_errors" in report
    paths = [e["path"] for e in report["schema_load_errors"]]
    assert any("broken.yml" in p for p in paths)


# ---------------------------------------------------------------------------
# Task 3 (proposed sidecar skip): lint must not surface .proposed.md files
# ---------------------------------------------------------------------------

def test_lint_skips_proposed_sidecars(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import lint, merge
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/concepts/a.md": "---\ntitle: A\ntype: concept\n---\n\n## Summary\n\na\n",
        "wiki/concepts/b.md": "---\ntitle: B\ntype: concept\n---\n\n## Summary\n\nb\n",
    })
    merge.stage(db, vault_id=vid, source_relpath="wiki/concepts/a.md",
                target_relpath="wiki/concepts/b.md")
    report = lint.check(db, vault_id=vid)
    import json
    blob = json.dumps(report)
    assert ".proposed" not in blob
