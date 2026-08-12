"""User-facing omw CLI."""
import json
import os
import stat
from pathlib import Path

import pytest

from scripts import omw_cli, registry, reindex
from scripts.paths import registry_path


def _run(argv):
    return omw_cli.main(argv)


def _seed_vault(tmp_path, name="v1"):
    from scripts.paths import ensure_home
    ensure_home()
    db = registry_path()
    root = tmp_path / name
    root.mkdir()
    registry.init_db(db)
    registry.add_vault(db, name=name, path=root, type_="markdown", mode="wiki")
    return db


def test_status_emits_setup_when_empty(capsys, monkeypatch):
    monkeypatch.setattr("scripts.paths.legacy_registry_candidates", lambda: [])
    assert _run(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["needs"] == "setup" and out["vault_count"] == 0


def test_status_surfaces_migrate_when_legacy_present(tmp_path, capsys, monkeypatch):
    # legacy registry exists, global one absent → omw status must report migrate,
    # and must NOT mask it by creating the global registry first.
    legacy = tmp_path / "legacy" / "registry.db"
    legacy.parent.mkdir(parents=True)
    registry.init_db(legacy)
    root = tmp_path / "c"
    root.mkdir()
    registry.add_vault(legacy, name="old", path=root, type_="markdown", mode="memo")
    monkeypatch.setattr("scripts.paths.legacy_registry_candidates", lambda: [legacy])
    assert _run(["status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["needs"] == "migrate"
    assert not registry_path().exists()   # status must not have created/masked it


def test_vault_list_empty(capsys):
    assert _run(["vault", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_vault_list_shows_seeded(tmp_path, capsys):
    _seed_vault(tmp_path, "v1")
    assert _run(["vault", "list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [v["name"] for v in data] == ["v1"]
    assert data[0]["mode"] == "wiki" and "is_active" in data[0]


def test_vault_create_global_default(capsys):
    assert _run(["vault", "create", "ai-agents", "--mode", "wiki", "--type", "markdown"]) == 0
    rows = registry.list_vaults(registry_path())
    assert [v["name"] for v in rows] == ["ai-agents"]
    v = rows[0]
    assert v["mode"] == "wiki" and v["type"] == "markdown" and bool(v["is_active"])
    root = Path(v["path"])
    assert (root / "wiki" / "entities").is_dir()
    assert (root / "wiki" / "index.md").is_file()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("memo", "inbox"),
        ("personal", "journal"),
        ("book", "chapters"),
        ("business", "meetings"),
        ("github-codebase", "modules"),
        ("website", "pages"),
    ],
)
def test_vault_create_supports_every_mode(mode, expected, capsys):
    assert _run(["vault", "create", f"v-{mode}", "--mode", mode]) == 0
    row = registry.list_vaults(registry_path())[0]
    assert row["mode"] == mode
    assert (Path(row["path"]) / expected).is_dir()


def test_vault_create_duplicate_errors(capsys):
    assert _run(["vault", "create", "dup"]) == 0
    capsys.readouterr()  # drain first create output
    assert _run(["vault", "create", "dup"]) == 1
    assert "already registered" in capsys.readouterr().err


def test_vault_create_project_location(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _run(["vault", "create", "p", "--location", "project"]) == 0
    v = registry.list_vaults(registry_path())[0]
    assert Path(v["path"]) == (tmp_path / ".omw" / "p")


def test_vault_use_switches_active(capsys):
    _run(["vault", "create", "a"])
    _run(["vault", "create", "b"])
    assert _run(["vault", "use", "a"]) == 0
    active = [v["name"] for v in registry.list_vaults(registry_path()) if v["is_active"]]
    assert active == ["a"]


def test_vault_use_unknown_errors(tmp_path, capsys):
    # Registry exists but the requested vault does not → VaultError "not found".
    _seed_vault(tmp_path, "exists")
    assert _run(["vault", "use", "nope"]) == 1
    assert "not found" in capsys.readouterr().err


def test_vault_use_no_registry_errors(capsys):
    assert _run(["vault", "use", "nope"]) == 1
    assert "no registry" in capsys.readouterr().err


def test_vault_forget_removes_row_keeps_files(capsys):
    _run(["vault", "create", "gone"])
    path = Path([v["path"] for v in registry.list_vaults(registry_path())][0])
    assert _run(["vault", "forget", "gone"]) == 0
    assert registry.list_vaults(registry_path()) == []
    assert path.is_dir()


def test_lint_active_vault_returns_report(capsys):
    _run(["vault", "create", "lv", "--mode", "wiki"])
    capsys.readouterr()  # drain vault create output
    assert _run(["lint"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)


def test_lint_no_active_errors(tmp_path, capsys):
    # Registry exists with a vault but none active → "no active vault".
    _seed_vault(tmp_path, "lv")  # add_vault leaves is_active = 0
    assert _run(["lint"]) == 1
    assert "no active vault" in capsys.readouterr().err


def test_lint_no_registry_errors(capsys):
    assert _run(["lint"]) == 1
    assert "no registry" in capsys.readouterr().err


def test_lint_vault_flag_no_registry_errors(capsys):
    assert _run(["lint", "--vault", "foo"]) == 1
    assert "no registry" in capsys.readouterr().err


@pytest.mark.parametrize("op,placeholder", [
    ("ingest", "path/to/file"),
    ("query", "what is this?"),
    ("autoresearch", "research topic"),
    ("persona-factcheck", "page.md"),
])
def test_agentic_op_prints_procedure_card(op, placeholder, capsys):
    """Agentic ops now require args and print a procedure card (not a Claude bridge)."""
    assert _run([op, placeholder]) == 0
    out = capsys.readouterr().out
    assert f"procedure: {op}" in out
    db = registry_path()
    assert (not db.exists()) or registry.list_vaults(db) == []


def test_installer_is_executable_and_valid():
    p = Path(__file__).resolve().parents[1] / "bin" / "omw-install.sh"
    assert p.is_file()
    assert os.stat(p).st_mode & stat.S_IXUSR, "omw-install.sh must be executable"
    text = p.read_text()
    assert "omw setup" in text                 # auto-launches the wizard
    assert "pipx install" in text or "pip install" in text


def test_omw_search_returns_json(capsys, monkeypatch):
    import scripts.search as _search
    monkeypatch.setattr(_search, "search_with_fallback",
                        lambda q, *, provider=None, limit=10: {
                            "results": [{"title": "T", "url": "u", "snippet": "s"}],
                            "provider": "brave",
                            "tried": ["brave"],
                        })
    assert _run(["search", "ai agents", "--limit", "3"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["provider"] == "brave"
    assert out["results"] == [{"title": "T", "url": "u", "snippet": "s"}]


def test_omw_search_no_fallback_returns_bare_list(capsys, monkeypatch):
    import scripts.search as _search
    monkeypatch.setattr(_search, "search",
                        lambda q, *, provider=None, limit=10: [{"title": "T", "url": "u", "snippet": "s"}])
    assert _run(["search", "ai agents", "--no-fallback", "--limit", "3"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"title": "T", "url": "u", "snippet": "s"}]


def test_omw_search_unconfigured_errors(capsys, monkeypatch):
    import scripts.search as _search
    from scripts.search.base import SearchError
    monkeypatch.setattr(_search, "search_with_fallback",
                        lambda q, *, provider=None, limit=10: (_ for _ in ()).throw(
                            SearchError("no provider configured — run omw setup search")))
    rc = _run(["search", "q"])
    assert rc == 1
    assert "omw setup search" in capsys.readouterr().err


def test_serve_help_exits_zero():
    import pytest
    with pytest.raises(SystemExit) as exc:
        omw_cli.main(["serve", "--help"])
    assert exc.value.code == 0


def test_serve_without_token_exits_1(monkeypatch, capsys):
    monkeypatch.delenv("OMW_SERVE_TOKEN", raising=False)
    # autouse OMW_HOME isolation guarantees no ~/.omw/.env token exists
    rc = omw_cli.main(["serve"])
    assert rc == 1
    assert "OMW_SERVE_TOKEN" in capsys.readouterr().err


def test_setup_serve_via_cli_writes_token():
    from scripts import omw_cli, config
    rc = omw_cli.main(["setup", "serve", "--token", "xyz789"])
    assert rc == 0
    assert config.read_secret("OMW_SERVE_TOKEN") == "xyz789"


def test_setup_personas_via_cli(tmp_path):
    from scripts import omw_cli, config
    rc = omw_cli.main([
        "setup", "personas", "--enable", "fact-checker,curator",
        "--main", "curator", "--host", "claude", "--base-dir", str(tmp_path),
    ])
    assert rc == 0
    assert config.load_config()["personas"]["main"] == "curator"
    assert (tmp_path / "CLAUDE.md").exists()


def test_setup_no_section_noninteractive_creates_vault(tmp_path, monkeypatch):
    from scripts import omw_cli, registry
    from scripts.paths import registry_path
    rc = omw_cli.main(["setup", "--noninteractive", "--name", "wiz"])
    assert rc == 0
    names = {v["name"] for v in registry.list_vaults(registry_path())}
    assert "wiz" in names


def test_setup_no_section_interactive_calls_run_all(monkeypatch):
    from scripts import omw_cli, setup_wizard
    called = {}
    monkeypatch.setattr(setup_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup_wizard, "run_all", lambda **k: called.update(ran=True) or 0)
    rc = omw_cli.main(["setup"])
    assert rc == 0 and called.get("ran") is True


def test_omw_import_folder_via_cli(tmp_path):
    from scripts import omw_cli, registry
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    vroot = tmp_path / "cv"; (vroot / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="cv", path=str(vroot), type_="markdown", mode="wiki")
    src = tmp_path / "s"; src.mkdir()
    (src / "x.md").write_text("hello", encoding="utf-8")
    rc = omw_cli.main(["import", "--source", "folder", "--src-dir", str(src), "--vault", "cv"])
    assert rc == 0
    assert (vroot / "raw" / "import" / "x.md").exists()


def test_omw_import_notion_no_token_exits_1(monkeypatch, capsys):
    from scripts import omw_cli
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    rc = omw_cli.main(["import", "--source", "notion", "--notion-id", "P1"])
    assert rc == 1
    assert "setup import" in capsys.readouterr().err.lower()


def test_schema_list_prints_types(capsys):
    rc = omw_cli.main(["schema", "list"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    names = {row["type"] for row in out}
    assert {"entity", "concept", "meta"} <= names


def test_schema_show_entity(capsys):
    rc = omw_cli.main(["schema", "show", "entity"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["type"] == "entity"
    assert "## Summary" in out["required_sections"]


def test_schema_show_unknown_type_exits_1(capsys):
    rc = omw_cli.main(["schema", "show", "nope"])
    assert rc == 1
    assert "valid types" in capsys.readouterr().err.lower()


def test_schema_show_no_registry_exits_1(capsys):
    # No registry at all → unified "no registry" message via _require_vault_row.
    rc = omw_cli.main(["schema", "show", "entity", "--vault", "ghost"])
    assert rc == 1
    assert "no registry" in capsys.readouterr().err.lower()


def test_schema_show_missing_vault_exits_1(tmp_path, capsys):
    # Registry exists but vault name not found → "not found" message.
    _seed_vault(tmp_path, "exists")
    rc = omw_cli.main(["schema", "show", "entity", "--vault", "ghost"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_supersede_marks_page(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki" / "concepts").mkdir(parents=True)
    vault = registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    (root / "wiki" / "concepts" / "old.md").write_text(
        "---\ntitle: Old\ntype: concept\n---\nbody\n", encoding="utf-8")
    reindex.full(db, vault_id=vault["id"])
    rc = omw_cli.main(["supersede", "wiki/concepts/old.md", "--by", "new", "--vault", "cv"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "superseded" and out["superseded_by"] == "new"


def test_supersede_missing_page_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki").mkdir(parents=True)
    registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    rc = omw_cli.main(["supersede", "wiki/nope.md", "--by", "x", "--vault", "cv"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def _review_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki" / "concepts").mkdir(parents=True)
    v = registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    return db, root, v["id"]


def test_review_due_lists(tmp_path, monkeypatch, capsys):
    db, root, vid = _review_vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "p.md").write_text(
        "---\ntitle: P\ntype: concept\n---\nx\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    rc = omw_cli.main(["review", "due", "--vault", "cv", "--today", "2026-05-31"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["relpath"] == "wiki/concepts/p.md" for r in rows)


def test_review_done_reschedules(tmp_path, monkeypatch, capsys):
    db, root, vid = _review_vault(tmp_path, monkeypatch)
    (root / "wiki" / "concepts" / "p.md").write_text(
        "---\ntitle: P\ntype: concept\nconfidence: high\n---\nx\n", encoding="utf-8")
    reindex.full(db, vault_id=vid)
    rc = omw_cli.main(["review", "done", "wiki/concepts/p.md", "--grade", "pass",
                       "--vault", "cv", "--today", "2026-05-31"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["review"]["due"] == "2026-08-29"


def test_review_done_missing_page_exits_1(tmp_path, monkeypatch, capsys):
    db, root, vid = _review_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["review", "done", "wiki/concepts/nope.md", "--grade", "pass",
                       "--vault", "cv"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def _links_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki" / "entities").mkdir(parents=True)
    v = registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    (root / "wiki" / "entities" / "k.md").write_text(
        "---\ntitle: Karp\ntype: entity\n---\n## Summary\nx\n", encoding="utf-8")
    (root / "wiki" / "entities" / "t.md").write_text(
        "---\ntitle: T\ntype: concept\n---\n## Summary\nKarp is great.\n", encoding="utf-8")
    reindex.full(db, vault_id=v["id"])
    return db, root, v["id"]


def test_links_suggest_lists(tmp_path, monkeypatch, capsys):
    _links_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["links", "suggest", "--vault", "cv"])
    assert rc == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["target_slug"] == "k" and r["src_relpath"] == "wiki/entities/t.md" for r in rows)


def test_links_link_inserts(tmp_path, monkeypatch, capsys):
    _links_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["links", "link", "wiki/entities/t.md", "--to", "k", "--vault", "cv"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["target_slug"] == "k" and out["inserted"].startswith("[[k")


def test_links_link_batch_from_suggestions(tmp_path, monkeypatch, capsys):
    _db, root, _vid = _links_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["links", "link", "--from-suggestions", "--vault", "cv"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["counts"] == {"applied": 1, "skipped": 0, "failed": 0}
    assert "[[k|Karp]]" in (root / "wiki" / "entities" / "t.md").read_text()


def test_links_link_missing_page_exits_1(tmp_path, monkeypatch, capsys):
    _links_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["links", "link", "wiki/entities/nope.md", "--to", "k", "--vault", "cv"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def _fields_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki" / "concepts").mkdir(parents=True)
    registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    (root / "wiki" / "concepts" / "p.md").write_text(
        "---\ntitle: P\ntype: concept\n---\n## Summary\nowner:: dante\nstatus:: active\n", encoding="utf-8")
    return db, root


def test_fields_prints_frontmatter_and_inline(tmp_path, monkeypatch, capsys):
    _fields_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["fields", "wiki/concepts/p.md", "--vault", "cv"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["frontmatter"]["title"] == "P"
    assert out["inline"]["owner"] == ["dante"]
    assert out["inline"]["status"] == ["active"]


def test_fields_missing_page_exits_1(tmp_path, monkeypatch, capsys):
    _fields_vault(tmp_path, monkeypatch)
    rc = omw_cli.main(["fields", "wiki/concepts/nope.md", "--vault", "cv"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_fields_serializes_date_frontmatter(tmp_path, monkeypatch, capsys):
    # YAML parses `date: 2026-06-01` to a datetime.date — json.dumps must not crash.
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts.paths import registry_path
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "cv"
    (root / "wiki" / "concepts").mkdir(parents=True)
    registry.add_vault(db, name="cv", path=str(root), type_="markdown", mode="wiki")
    (root / "wiki" / "concepts" / "d.md").write_text(
        "---\ntitle: D\ndate: 2026-06-01\ntype: concept\ntags: [x]\n---\n## Summary\nx\n",
        encoding="utf-8")
    rc = omw_cli.main(["fields", "wiki/concepts/d.md", "--vault", "cv"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["frontmatter"]["date"] == "2026-06-01"  # date serialized as ISO string


def test_maint_status_json(capsys, monkeypatch):
    import json
    from scripts import omw_cli
    monkeypatch.setattr("scripts.maint.status", lambda *a, **k: {
        "stale": 1, "expired": 0, "lint_issues": 0, "nudge": "x"})
    monkeypatch.setattr(omw_cli, "_require_vault_row",
                        lambda db, name: {"id": 1, "path": "/tmp/v"})

    class _DB:
        def exists(self):
            return True

    monkeypatch.setattr(omw_cli, "registry_path", lambda: _DB())
    rc = omw_cli.main(["maint", "status"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["stale"] == 1


def test_maint_status_exit_code(monkeypatch):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.maint.status", lambda *a, **k: {
        "stale": 1, "expired": 0, "lint_issues": 0, "nudge": "x"})
    class _DB:
        def exists(self):
            return True
    monkeypatch.setattr(omw_cli, "registry_path", lambda: _DB())
    monkeypatch.setattr(omw_cli, "_require_vault_row", lambda db, name: {"id": 1, "path": "/tmp/v"})
    assert omw_cli.main(["maint", "status", "--exit-code"]) == 1


def test_connections_json(capsys, monkeypatch):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.community.analyze", lambda *a, **k: {
        "modularity": 0.5, "communities": [{"id": 0, "size": 2, "members": ["wiki/a.md", "wiki/b.md"]}],
        "bridges": [], "hubs": []})
    class _DB:
        def exists(self):
            return True
    monkeypatch.setattr(omw_cli, "registry_path", lambda: _DB())
    monkeypatch.setattr(omw_cli, "_require_vault_row", lambda db, name: {"id": 1, "path": "/tmp/v"})
    rc = omw_cli.main(["connections"])
    import json
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["modularity"] == 0.5


def test_cli_setup_recall_accepts_embed_flags(tmp_path, monkeypatch):
    from scripts import omw_cli, config
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    rc = omw_cli.main(["setup", "recall", "--noninteractive", "--strategy", "embedding",
                       "--embed-provider", "openai", "--embed-dim", "1536", "--base-dir", str(tmp_path)])
    assert rc == 0
    assert config.load_config()["recall"]["embedding"]["provider"] == "openai"


def test_cli_setup_recall_accepts_knowledge_candidate_mode(tmp_path, monkeypatch):
    from scripts import omw_cli, config
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    rc = omw_cli.main([
        "setup", "recall", "--noninteractive", "--base-dir", str(tmp_path),
        "--knowledge-candidates", "staged",
    ])
    assert rc == 0
    assert config.load_config()["recall"]["knowledge_candidates"] == "staged"


def test_cli_recall_accepts_hook_format_flags(monkeypatch, capsys):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.recall.prompt", lambda text, **_kwargs: "ctx")
    rc = omw_cli.main(["recall", "prompt", "--format", "claude-json",
                       "--event", "UserPromptSubmit", "--text", "hello wiki"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert out["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_cli_recall_accepts_codex_json_format(monkeypatch, capsys):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.recall.prompt", lambda text, **_kwargs: "ctx")
    rc = omw_cli.main(["recall", "prompt", "--format", "codex-json",
                       "--event", "UserPromptSubmit", "--text", "hello wiki"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert out["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_cli_recall_pretool_accepts_hook_format_flags(monkeypatch, capsys):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.recall.pretool", lambda payload: "ctx")
    rc = omw_cli.main(["recall", "pretool", "--format", "claude-json",
                       "--event", "PreToolUse"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["additionalContext"] == "ctx"


def test_cli_recall_capture_stores_and_always_emits_json_noop(monkeypatch, capsys):
    from scripts import omw_cli
    seen = {}
    monkeypatch.setattr("scripts.recall.capture_session", lambda **kwargs: seen.update(kwargs) or {"stored": True})
    rc = omw_cli.main(["recall", "capture", "--format", "codex-json",
                       "--event", "Stop", "--source", "stop", "--host", "codex"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"continue": True}
    assert seen["host"] == "codex" and seen["source"] == "stop"


def test_cli_recall_sessions_lists_and_dismisses(monkeypatch, capsys):
    from scripts import omw_cli
    monkeypatch.setattr("scripts.recall.session_captures", lambda limit=20: [{"id": 7}])
    monkeypatch.setattr("scripts.recall.dismiss_session", lambda capture_id: capture_id == 7)

    assert omw_cli.main(["recall", "sessions", "--limit", "3"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"id": 7}]
    assert omw_cli.main(["recall", "sessions", "--dismiss", "7"]) == 0
    assert json.loads(capsys.readouterr().out) == {"dismissed": 7}


def test_require_vault_row_consistent_errors(tmp_path, monkeypatch, capsys):
    from scripts import omw_cli, registry
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = omw_cli.registry_path(); registry.init_db(db)
    root = tmp_path / "v"; root.mkdir()
    registry.add_vault(db, name="v", path=str(root), type_="markdown", mode="wiki")
    # explicit bad name → specific message
    assert omw_cli._require_vault_row(db, "nope") is None
    assert "vault 'nope' not found" in capsys.readouterr().err
    # explicit good name → row
    assert omw_cli._require_vault_row(db, "v")["name"] == "v"


def test_cmd_import_missing_vault_uses_consistent_message(tmp_path, monkeypatch, capsys):
    # _cmd_import previously printed a generic "no vault"; now it must match the others
    from scripts import omw_cli, registry
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    db = omw_cli.registry_path(); registry.init_db(db)
    src = tmp_path / "s"; src.mkdir(); (src / "x.md").write_text("hi", encoding="utf-8")
    rc = omw_cli.main(["import", "--source", "folder", "--src-dir", str(src), "--vault", "ghost"])
    assert rc == 1 and "vault 'ghost' not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# reindex command + connections auto-reindex (body [[wikilinks]] → graph)
# ---------------------------------------------------------------------------

def _write_page(conc, name, refs):
    body = " ".join(f"[[{r}]]" for r in refs)
    (conc / f"{name}.md").write_text(
        f"---\ntitle: {name}\ntype: concept\ntags: [t]\n---\nrelated: {body}\n",
        encoding="utf-8",
    )


def test_connections_auto_reindexes_body_wikilinks(capsys):
    """Pages written directly (as an agent does during ingest) must show up in the
    connections graph without a manual reindex — this was the empty-graph bug."""
    assert _run(["vault", "create", "graphtest", "--mode", "wiki", "--type", "markdown"]) == 0
    capsys.readouterr()
    db = registry_path()
    vid = next(v["id"] for v in registry.list_vaults(db) if v["name"] == "graphtest")
    conc = registry.get_vault_root(db, vid) / "wiki" / "concepts"
    conc.mkdir(parents=True, exist_ok=True)
    _write_page(conc, "alpha", ["beta", "gamma"])
    _write_page(conc, "beta", ["alpha", "gamma"])
    _write_page(conc, "gamma", ["alpha", "beta"])

    # --no-reindex reads the stale index → the freshly-written links are invisible
    assert _run(["connections", "--no-reindex"]) == 0
    assert json.loads(capsys.readouterr().out)["communities"] == []

    # default connections auto-reindexes → the triangle becomes one community
    assert _run(["connections"]) == 0
    rep = json.loads(capsys.readouterr().out)
    members = {m for c in rep["communities"] for m in c["members"]}
    assert any("alpha" in m for m in members)
    assert any("beta" in m for m in members)
    assert any("gamma" in m for m in members)


def test_connections_empty_graph_prints_hint(capsys):
    """An empty connections graph must nudge the user toward linking pages."""
    assert _run(["vault", "create", "emptyg", "--mode", "wiki", "--type", "markdown"]) == 0
    capsys.readouterr()
    assert _run(["connections"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out)["communities"] == []
    assert "empty graph" in out.err and "[[wikilinks]]" in out.err


def test_reindex_command_reports_indexed_count(capsys):
    assert _run(["vault", "create", "rx", "--mode", "wiki", "--type", "markdown"]) == 0
    capsys.readouterr()
    assert _run(["reindex"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["vault"] == "rx" and out["mode"] == "incremental" and "indexed" in out
    assert _run(["reindex", "--full"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "full"
