import json
from scripts import omw_cli
from scripts import ops_registry as reg


def test_report_registered_deterministic():
    assert reg.get("report") is not None
    assert reg.get("report").kind == "deterministic"
    assert reg.get("report").phase == "meta"


def test_cli_report_text(tmp_path, monkeypatch, capsys):
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={
        "raw/a.md": "# A\n\nx", "wiki/concepts/c.md": "# C\n\ny"})
    rc = omw_cli.main(["report"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VAULTS" in out and "ACTIVE VAULT" in out and "HEALTH" in out


def test_cli_report_json(tmp_path, monkeypatch, capsys):
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    rc = omw_cli.main(["report", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["vaults"]["total"] == 1
    assert "health" in data and "active_vault" in data


def test_cli_report_bad_vault_errors(tmp_path, monkeypatch, capsys):
    from tests.conftest import make_vault_with_pages
    make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    rc = omw_cli.main(["report", "--vault", "does-not-exist"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "not found" in err


def test_cli_report_no_active_vault_shows_header(tmp_path, monkeypatch, capsys):
    # registry exists but no active vault → all-vaults dashboard, exit 0
    omw_home = tmp_path / ".omw"
    (omw_home / "vaults").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OMW_HOME", str(omw_home))
    from scripts import registry
    registry.init_db(omw_home / "registry.db")
    rc = omw_cli.main(["report"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VAULTS" in out and "no active vault" in out
