import json
from pathlib import Path

from scripts import omw_cli
from scripts import ops_registry as reg


def test_uninstall_registered_deterministic_meta():
    spec = reg.get("uninstall")
    assert spec is not None and spec.kind == "deterministic" and spec.phase == "meta"


def _seed_proj(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    (tmp_path / ".omw").mkdir(parents=True, exist_ok=True)
    base = tmp_path / "proj"
    base.mkdir()
    (base / "CLAUDE.md").write_text(
        "user.\n\n<!-- omw-recall:start -->\n## m\n\nx\n<!-- omw-recall:end -->\n", encoding="utf-8")
    return base


def test_cli_dry_run_mutates_nothing(tmp_path, monkeypatch, capsys):
    base = _seed_proj(tmp_path, monkeypatch)
    before = (base / "CLAUDE.md").read_text(encoding="utf-8")
    rc = omw_cli.main(["uninstall", "--dry-run", "--host", "claude", "--base-dir", str(base)])
    out = capsys.readouterr().out
    assert rc == 0
    assert (base / "CLAUDE.md").read_text(encoding="utf-8") == before
    assert "omw-recall" in out or "claude" in out  # plan surfaced


def test_cli_noninteractive_tier1_strips_block(tmp_path, monkeypatch):
    base = _seed_proj(tmp_path, monkeypatch)
    monkeypatch.setattr(omw_cli.sys.stdin, "isatty", lambda: False)
    rc = omw_cli.main(["uninstall", "--yes", "--host", "claude", "--base-dir", str(base)])
    assert rc == 0
    assert "omw-recall" not in (base / "CLAUDE.md").read_text(encoding="utf-8")


def test_cli_vaults_refused_without_yes_noninteractive(tmp_path, monkeypatch, capsys):
    base = _seed_proj(tmp_path, monkeypatch)
    monkeypatch.setattr(omw_cli.sys.stdin, "isatty", lambda: False)
    rc = omw_cli.main(["uninstall", "--vaults", "--host", "claude", "--base-dir", str(base)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "vaults" in err.lower() or "yes" in err.lower()
