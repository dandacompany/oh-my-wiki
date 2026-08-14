import json
from pathlib import Path

from scripts import omw_cli, registry
from scripts.paths import registry_path


def _active_vault(tmp_path, mode="wiki"):
    assert omw_cli.main(["vault", "create", "v", "--mode", mode]) == 0
    row = registry.get_active(registry_path())
    return Path(row["path"])


def test_capture_local_markdown_saves_raw_and_indexes_it(tmp_path, capsys):
    root = _active_vault(tmp_path)
    capsys.readouterr()
    source = tmp_path / "source.md"
    source.write_text("source body", encoding="utf-8")

    assert omw_cli.main([
        "capture", str(source), "--title", "Source", "--date", "2026-08-14"
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["relpath"] == "raw/2026-08-14-source.md"
    assert (root / result["relpath"]).read_text(encoding="utf-8") == "source body"
    conn = registry.connect(registry_path())
    try:
        assert conn.execute(
            "SELECT 1 FROM notes WHERE vault_id = ? AND relpath = ?",
            (registry.get_active(registry_path())["id"], result["relpath"]),
        ).fetchone() is not None
    finally:
        conn.close()


def test_page_write_creates_schema_page_updates_index_log_and_index(tmp_path, capsys):
    root = _active_vault(tmp_path)
    capsys.readouterr()
    body = tmp_path / "body.md"
    body.write_text("A concise summary.", encoding="utf-8")

    assert omw_cli.main([
        "page", "write", "--layer", "summaries", "--title", "Source",
        "--body-file", str(body), "--tags", "one,two", "--date", "2026-08-14",
        "--source-raw", "raw/2026-08-14-source.md", "--index", "One line",
        "--log-op", "ingest",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    page = root / result["relpath"]
    assert page.is_file()
    assert "source_raw:" in page.read_text(encoding="utf-8")
    assert "[[source]]" in (root / "wiki/index.md").read_text(encoding="utf-8")
    assert "ingest | Source" in (root / "wiki/log.md").read_text(encoding="utf-8")
    conn = registry.connect(registry_path())
    try:
        assert conn.execute(
            "SELECT 1 FROM notes WHERE vault_id = ? AND relpath = ?",
            (registry.get_active(registry_path())["id"], result["relpath"]),
        ).fetchone() is not None
    finally:
        conn.close()


def test_research_cli_exposes_session_state_without_module_invocation(tmp_path, capsys):
    _active_vault(tmp_path)
    capsys.readouterr()

    assert omw_cli.main(["research", "init", "--query", "agent memory"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert Path(result["session_dir"], "mission.json").is_file()


def test_page_write_synthesis_records_citations_and_required_sources(tmp_path, capsys):
    root = _active_vault(tmp_path)
    capsys.readouterr()
    body = tmp_path / "synthesis.md"
    body.write_text("Grounded answer.", encoding="utf-8")

    assert omw_cli.main([
        "page", "write", "--layer", "syntheses", "--title", "Answer",
        "--body-file", str(body), "--date", "2026-08-14",
        "--citation", "wiki/concepts/source.md",
    ]) == 0

    result = json.loads(capsys.readouterr().out)
    text = (root / result["relpath"]).read_text(encoding="utf-8")
    assert "synthesizes:" in text
    assert "wiki/concepts/source.md" in text
    assert "## Sources" in text


def test_procedure_docs_use_only_the_public_omw_cli():
    commands = Path(__file__).resolve().parents[1] / "commands"
    forbidden = ("python3 -m scripts", "from scripts import")
    offenders = {
        path.name: marker
        for path in commands.rglob("*.md")
        for marker in forbidden
        if marker in path.read_text(encoding="utf-8")
    }
    assert offenders == {}
