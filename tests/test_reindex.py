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
    n_indexed = reindex.full(db, vault_id=vid)["indexed"]
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
    count = reindex.full(db, vault_id=vid)["indexed"]
    assert isinstance(count, int) and count == 1


def _entity(root, name):
    (root / "wiki" / "entities" / f"{name}.md").write_text(
        f"---\ntitle: {name}\ndate: 2026-01-01\ntype: entity\ntags: [x]\n---\n## Summary\nx\n",
        encoding="utf-8")


def test_full_prunes_orphan_rows_for_hand_deleted_files(tmp_path, monkeypatch):
    """A hand-deleted file's registry row is pruned on the next full reindex —
    closes the gap where lint.drift.missing_files lingered with no CLI fix."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    _entity(root, "a")
    _entity(root, "b")
    res = reindex.full(db, vault_id=vid)
    assert res["indexed"] == 2 and res["pruned"] == []

    (root / "wiki" / "entities" / "b.md").unlink()       # hand-delete one file
    res2 = reindex.full(db, vault_id=vid)
    assert res2["indexed"] == 1
    assert res2["pruned"] == ["wiki/entities/b.md"]
    relpaths = {n["relpath"] for n in registry.list_notes(db, vault_id=vid)}
    assert "wiki/entities/b.md" not in relpaths           # orphan row gone
    assert "wiki/entities/a.md" in relpaths               # survivor untouched


def test_incremental_never_prunes(tmp_path, monkeypatch):
    """Incremental sees only changed files, so its `seen` is partial — must not prune."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    _entity(root, "a")
    reindex.full(db, vault_id=vid)
    (root / "wiki" / "entities" / "a.md").unlink()
    reindex.incremental(db, vault_id=vid)
    relpaths = {n["relpath"] for n in registry.list_notes(db, vault_id=vid)}
    assert "wiki/entities/a.md" in relpaths               # left for a full reindex to prune


def test_scan_reports_schema_issues_but_still_ingests(tmp_path, monkeypatch):
    db, root, vid = _vault(tmp_path, monkeypatch)
    # entity missing required ## Summary section
    (root / "wiki" / "entities" / "bad.md").write_text(
        "---\ntitle: T\ndate: 2026-01-01\ntype: entity\ntags: [a]\n---\nno section\n",
        encoding="utf-8",
    )
    vp = registry.get_vault_root(db, vid)
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
    vp = registry.get_vault_root(db, vid)
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
    count = reindex.full(db, vault_id=vid)["indexed"]  # must not raise
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


# ---------------------------------------------------------------------------
# Task 1: changed-only embeddings (B) + surface FTS write errors (C)
# ---------------------------------------------------------------------------

def test_scan_reports_changed_relpaths_and_fts_errors(tmp_path, monkeypatch):
    """_scan returns 'changed' list with indexed relpaths and 'fts_errors' == []."""
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nbody\n",
        encoding="utf-8",
    )
    vp = registry.get_vault_root(db, vid)
    res = reindex._scan(db, vid, vp, incremental=False)
    assert "wiki/a.md" in res["changed"]
    assert res["fts_errors"] == []


def test_refresh_embeddings_only_targets_given_relpaths(tmp_path, monkeypatch):
    """refresh_embeddings(relpaths=[...]) only embeds the specified wiki/ pages."""
    captured = {}
    monkeypatch.setattr(
        "scripts.config.load_config",
        lambda: {"recall": {"embedding": {"provider": "fake", "dim": 8}}},
    )
    import scripts.vector_index as vi
    monkeypatch.setattr(vi, "available", lambda: True)
    monkeypatch.setattr(
        vi,
        "upsert",
        lambda db, *, vault_id, embedder, rows: captured.update(rows=rows) or len(rows),
    )
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    for n in ("a", "b"):
        (root / "wiki" / f"{n}.md").write_text(
            f"---\ntitle: {n}\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nb\n",
            encoding="utf-8",
        )
    reindex.full(db, vault_id=vid)
    # only embed wiki/a.md when restricted
    reindex.refresh_embeddings(db, vault_id=vid, relpaths=["wiki/a.md"])
    assert [r[0] for r in captured["rows"]] == ["wiki/a.md"]


def test_incremental_skips_embeddings_when_nothing_changed(tmp_path, monkeypatch):
    """incremental() must NOT call refresh_embeddings when no files changed."""
    calls = []
    monkeypatch.setattr(
        reindex,
        "refresh_embeddings",
        lambda *a, **k: calls.append(k.get("relpaths")) or 0,
    )
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nb\n",
        encoding="utf-8",
    )
    reindex.full(db, vault_id=vid)  # index it
    calls.clear()
    reindex.incremental(db, vault_id=vid)  # nothing changed since
    assert calls == []  # refresh_embeddings NOT called


def test_refresh_embeddings_warns_on_failure_not_silent(tmp_path, monkeypatch, capsys):
    from scripts import reindex
    monkeypatch.setattr("scripts.config.load_config",
                        lambda: {"recall": {"embedding": {"provider": "fake", "dim": 8}}})
    import scripts.vector_index as vi
    monkeypatch.setattr(vi, "available", lambda: True)
    monkeypatch.setattr(vi, "upsert", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    db, root, vid = _vault(tmp_path, monkeypatch)   # use the existing helper in test_reindex.py
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "a.md").write_text("---\ntitle: A\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nb\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    n = reindex.refresh_embeddings(db, vault_id=vid, relpaths=["wiki/a.md"])
    assert n == 0                                  # best-effort, did not raise
    assert "embedding refresh failed" in capsys.readouterr().err   # but warned (not silent)


def test_refresh_embeddings_warns_on_config_failure_not_raise(tmp_path, monkeypatch, capsys):
    from scripts import reindex
    monkeypatch.setattr("scripts.config.load_config",
                        lambda: (_ for _ in ()).throw(RuntimeError("bad config.yaml")))
    db, root, vid = _vault(tmp_path, monkeypatch)
    n = reindex.refresh_embeddings(db, vault_id=vid)        # must NOT raise
    assert n == 0 and "embedding refresh failed" in capsys.readouterr().err


def test_incremental_surfaces_embedding_config_failure(tmp_path, monkeypatch, capsys):
    from scripts import reindex
    db, root, vid = _vault(tmp_path, monkeypatch)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "a.md").write_text("---\ntitle: A\ndate: 2026-01-01\ntype: concept\ntags: [x]\n---\nb\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    # now break config so the changed-page embedding attempt fails
    monkeypatch.setattr("scripts.config.load_config",
                        lambda: (_ for _ in ()).throw(RuntimeError("bad config")))
    (root / "wiki" / "a.md").write_text("---\ntitle: A2\ndate: 2026-01-02\ntype: concept\ntags: [x]\n---\nchanged\n", encoding="utf-8")
    reindex.incremental(db, vault_id=vid)                    # must NOT raise
    assert "embedding refresh failed" in capsys.readouterr().err   # surfaced, not silent


def test_refresh_embeddings_strict_reraises(monkeypatch, tmp_path):
    from scripts import reindex

    def boom(*a, **k):
        raise RuntimeError("embed exploded")

    # reindex does `from scripts import embed` so reindex.embed.get_embedder is the target
    monkeypatch.setattr(reindex.embed, "get_embedder", boom)
    # strict=True surfaces the failure
    with pytest.raises(RuntimeError, match="exploded"):
        reindex.refresh_embeddings(tmp_path / "db.sqlite", vault_id=1, strict=True)
    # strict=False (default) swallows → returns 0
    assert reindex.refresh_embeddings(tmp_path / "db.sqlite", vault_id=1) == 0


# ---------------------------------------------------------------------------
# Non-UTF-8 notes must not abort reindex (omw setup section 'vault' regression)
# ---------------------------------------------------------------------------

@pytest.fixture
def cp949_vault(tmp_db, tmp_path):
    """A vault holding one good UTF-8 note and one CP949 (EUC-KR) note."""
    root = tmp_path / "vault"
    root.mkdir()
    (root / "good.md").write_text(
        "---\ntitle: Good\ntype: note\ntags: [ok]\n---\n정상 UTF-8 문서\n",
        encoding="utf-8",
    )
    (root / "legacy.md").write_bytes(
        "---\ntitle: Legacy\ntype: note\ntags: [old]\n---\n이 문서는 CP949입니다\n".encode("cp949")
    )
    registry.init_db(tmp_db)
    row = registry.add_vault(tmp_db, name="cp", path=root, type_="markdown", mode="memo")
    return tmp_db, row["id"], root


def test_full_reindex_survives_cp949_note(cp949_vault, capsys):
    db, vid, _root = cp949_vault
    result = reindex.full(db, vault_id=vid)          # must NOT raise
    assert result["indexed"] == 2
    assert result["decode_errors"] == ["legacy.md"]
    err = capsys.readouterr().err
    assert "legacy.md" in err and "UTF-8" in err     # offending file is named
    relpaths = {n["relpath"] for n in registry.list_notes(db, vault_id=vid)}
    assert {"good.md", "legacy.md"} <= relpaths


def test_full_reindex_decodes_utf16_bom_note_losslessly(tmp_db, tmp_path, capsys):
    root = tmp_path / "vault"
    root.mkdir()
    text = "---\ntitle: 노트패드\ntype: note\ntags: [win]\n---\n메모장 UTF-16 문서\n"
    (root / "notepad.md").write_bytes(text.encode("utf-16"))   # BOM included
    registry.init_db(tmp_db)
    row = registry.add_vault(tmp_db, name="u16", path=root, type_="markdown", mode="memo")
    result = reindex.full(tmp_db, vault_id=row["id"])
    assert result["decode_errors"] == ["notepad.md"]
    notes = registry.list_notes(tmp_db, vault_id=row["id"])
    assert notes[0]["title"] == "노트패드"                     # lossless UTF-16 recovery
    assert "decoded as UTF-16" in capsys.readouterr().err
