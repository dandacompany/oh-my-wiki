import json
import time

import pytest

from scripts import fts, registry, reindex


@pytest.fixture
def registered_markdown(tmp_db, markdown_vault_path):
    registry.init_db(tmp_db)
    row = registry.add_vault(
        tmp_db, name="md", path=markdown_vault_path,
        type_="markdown", mode="memo",
    )
    return tmp_db, row["id"]


def test_full_reindex_discovers_all_markdown_files(registered_markdown):
    db, vid = registered_markdown
    n_indexed = reindex.full(db, vault_id=vid)
    assert n_indexed == 6  # 5 with frontmatter + 1 without
    notes = registry.list_notes(db, vault_id=vid)
    titles = {n["title"] for n in notes if n["title"]}
    assert "Karpathy LLM Wiki Proposal" in titles


def test_full_reindex_marks_files_without_frontmatter_as_parse_error(registered_markdown):
    db, vid = registered_markdown
    reindex.full(db, vault_id=vid)
    parse_errors = [
        n for n in registry.list_notes(db, vault_id=vid) if n["parse_error"] == 1
    ]
    assert len(parse_errors) == 1
    assert parse_errors[0]["relpath"].endswith("no-frontmatter.md")


def test_incremental_skips_unchanged_files(registered_markdown, monkeypatch):
    db, vid = registered_markdown
    reindex.full(db, vault_id=vid)

    seen = []
    real_upsert = registry.upsert_note

    def spy(*args, **kwargs):
        seen.append(kwargs["relpath"])
        return real_upsert(*args, **kwargs)

    monkeypatch.setattr(registry, "upsert_note", spy)
    reindex.incremental(db, vault_id=vid)
    assert seen == [], "no files changed, so no upserts expected"


def test_incremental_picks_up_new_file(registered_markdown, markdown_vault_path):
    db, vid = registered_markdown
    reindex.full(db, vault_id=vid)
    new_file = markdown_vault_path / "inbox" / "scratch-temp.md"
    new_file.write_text("---\ntitle: Scratch\ntype: note\ntags: []\n---\nbody\n")
    try:
        time.sleep(0.05)
        reindex.incremental(db, vault_id=vid)
        notes = registry.list_notes(db, vault_id=vid)
        relpaths = {n["relpath"] for n in notes}
        assert "inbox/scratch-temp.md" in relpaths
    finally:
        new_file.unlink()


def test_obsidian_vault_layer_classification(tmp_db, obsidian_vault_path):
    registry.init_db(tmp_db)
    row = registry.add_vault(
        tmp_db, name="ob", path=obsidian_vault_path,
        type_="obsidian", mode="wiki",
    )
    reindex.full(tmp_db, vault_id=row["id"])
    layers = {
        n["relpath"]: n["layer"]
        for n in registry.list_notes(tmp_db, vault_id=row["id"])
    }
    assert layers["wiki/index.md"] == "meta"
    assert layers["wiki/log.md"] == "meta"
    assert layers["wiki/concepts/compounding-knowledge.md"] == "wiki"
    assert layers["raw/2026-04-04-llm-wiki-gist.md"] == "raw"


# ---------------------------------------------------------------------------
# CLI entry-point tests
# ---------------------------------------------------------------------------

def _seed_vault(tmp_db, tmp_path, name):
    registry.init_db(tmp_db)
    vroot = tmp_path / name
    (vroot / "wiki").mkdir(parents=True)
    row = registry.add_vault(tmp_db, name=name, path=str(vroot), type_="markdown", mode="wiki")
    (vroot / "wiki" / "a.md").write_text(
        "---\ntitle: a\ntype: concept\ndate: 2026-05-31\ntags: []\n---\n\nbody", encoding="utf-8")
    return row["id"], vroot


def test_reindex_cli_indexes_and_prints_json(tmp_db, tmp_path, capsys):
    vid, _ = _seed_vault(tmp_db, tmp_path, "rv")
    rc = reindex.main(["--vault-id", str(vid), "--db", str(tmp_db)])
    assert rc == 0
    notes = {n["relpath"] for n in registry.list_notes(tmp_db, vault_id=vid)}
    assert "wiki/a.md" in notes
    out = json.loads(capsys.readouterr().out)
    assert out["vault_id"] == vid
    assert out["mode"] == "incremental"
    assert out["indexed"] >= 1


def test_reindex_cli_full_flag(tmp_db, tmp_path, capsys):
    vid, _ = _seed_vault(tmp_db, tmp_path, "rv2")
    rc = reindex.main(["--vault-id", str(vid), "--db", str(tmp_db), "--full"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "full"


def test_reindex_cli_requires_vault_id():
    with pytest.raises(SystemExit):
        reindex.main(["--db", "/tmp/whatever.db"])


# ---------------------------------------------------------------------------
# Task 4: non-blocking schema tally
# ---------------------------------------------------------------------------

def _vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = tmp_path / "registry.db"
    registry.init_db(db)
    root = tmp_path / "vault"
    (root / "wiki" / "entities").mkdir(parents=True)
    v = registry.add_vault(db, name="v", path=root, type_="markdown", mode="wiki")
    return db, root, v["id"]


def test_full_returns_int_count(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "entities" / "ok.md").write_text(
        "---\ntitle: T\ndate: 2026-01-01\ntype: entity\ntags: [a]\n---\n## Summary\nx\n",
        encoding="utf-8",
    )
    count = reindex.full(db, vault_id=vid)
    assert isinstance(count, int) and count == 1


def test_scan_reports_schema_issues_but_still_ingests(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    # entity missing required ## Summary section
    (root / "wiki" / "entities" / "bad.md").write_text(
        "---\ntitle: T\ndate: 2026-01-01\ntype: entity\ntags: [a]\n---\nno section\n",
        encoding="utf-8",
    )
    vp = reindex._vault_path(db, vid)
    result = reindex._scan(db, vid, vp, incremental=False)
    assert result["indexed"] == 1
    flat = {i["issue"] for entry in result["schema_issues"] for i in entry["issues"]}
    assert "missing_section:## Summary" in flat
    # page is still indexed despite the violation
    assert any(n["relpath"] == "wiki/entities/bad.md"
               for n in registry.list_notes(db, vault_id=vid))


def test_scan_validates_pages_without_frontmatter(tmp_path, monkeypatch):
    # A page with NO frontmatter parses to empty meta without raising, so it
    # must be schema-validated in the tally (matching `lint`), not silently skipped.
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "entities" / "nofm.md").write_text(
        "just plain text, no frontmatter at all\n", encoding="utf-8",
    )
    vp = reindex._vault_path(db, vid)
    result = reindex._scan(db, vid, vp, incremental=False)
    flat = {i["issue"] for entry in result["schema_issues"]
            if entry["relpath"] == "wiki/entities/nofm.md" for i in entry["issues"]}
    assert "missing_field:type" in flat  # validated like lint, not skipped
    # still indexed (non-blocking)
    assert any(n["relpath"] == "wiki/entities/nofm.md"
               for n in registry.list_notes(db, vault_id=vid))


# ---------------------------------------------------------------------------
# Task 2 (F#6): FTS5 population during reindex
# ---------------------------------------------------------------------------

def test_reindex_populates_fts(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "entities" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\ntype: entity\ntags: [x]\n---\n## Summary\nthe quick brown fox\n",
        encoding="utf-8")
    reindex.full(db, vault_id=vid)
    conn = registry.connect(db)
    try:
        n = conn.execute("SELECT count(*) FROM notes_fts WHERE vault_id=?", (str(vid),)).fetchone()[0]
    finally:
        conn.close()
    assert n == 1
    # body term is searchable
    assert fts.search(db, vault_id=vid, query="fox", limit=5)[0]["relpath"] == "wiki/entities/a.md"


def test_reindex_works_without_fts5(tmp_path, monkeypatch):
    monkeypatch.setattr(fts, "fts5_available", lambda: False)
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki" / "entities" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\ntype: entity\ntags: [x]\n---\n## Summary\nx\n",
        encoding="utf-8")
    count = reindex.full(db, vault_id=vid)  # must not raise
    assert count == 1


# ---------------------------------------------------------------------------
# Task 4.3: refresh_embeddings
# ---------------------------------------------------------------------------

def test_refresh_embeddings_noop_when_unconfigured(tmp_path, monkeypatch):
    """refresh_embeddings returns 0 (no-op) when embedding provider is 'none'."""
    import scripts.config as _cfg
    monkeypatch.setattr(_cfg, "load_config", lambda: {"recall": {}})
    db, root, vid = _vault(tmp_path, monkeypatch)
    result = reindex.refresh_embeddings(db, vault_id=vid)
    assert result == 0
