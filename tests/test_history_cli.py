import json

import pytest

from scripts import omw_cli
from scripts import ops_registry as reg


def test_history_registered_deterministic_meta():
    spec = reg.get("history")
    assert spec is not None and spec.kind == "deterministic" and spec.phase == "meta"


def _seed(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    return make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})


def test_cli_log_then_show(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    rc = omw_cli.main(["history", "log", "--type", "generate", "--request", "make a slide",
                       "--summary", "made 1", "--ref", "wiki/concepts/x.md", "--tag", "slide"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["type"] == "generate"
    rc = omw_cli.main(["history", "show", str(out["id"])])
    shown = json.loads(capsys.readouterr().out)
    assert rc == 0 and shown["request"] == "make a slide" and shown["refs"] == ["wiki/concepts/x.md"]


def test_cli_log_bad_type_errors(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    # argparse rejects an out-of-enum --type at the parser layer (exit 2 via SystemExit).
    with pytest.raises(SystemExit) as exc:
        omw_cli.main(["history", "log", "--type", "nope", "--request", "x"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "invalid choice" in err or "nope" in err


def test_cli_similar_and_prefs(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    omw_cli.main(["history", "log", "--type", "generate", "--request", "slide about agents"])
    capsys.readouterr()
    rc = omw_cli.main(["history", "similar", "agents slide"])
    hits = json.loads(capsys.readouterr().out)
    assert rc == 0 and hits and hits[0]["score"] > 0
    rc = omw_cli.main(["history", "prefs"])
    p = json.loads(capsys.readouterr().out)
    assert rc == 0 and "focus_terms" in p


def test_cli_history_recreates_missing_table(tmp_path, monkeypatch, capsys):
    db, vid = _seed(tmp_path, monkeypatch)
    from scripts import registry
    conn = registry.connect(db)
    try:
        conn.execute("DROP TABLE interactions")
        conn.commit()
    finally:
        conn.close()
    # a pre-history DB: omw history must re-create the table and succeed
    rc = omw_cli.main(["history", "log", "--type", "query", "--request", "after upgrade"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["type"] == "query"


def test_cli_find_and_list_outcome(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch)
    omw_cli.main(["history", "log", "--type", "generate", "--request", "draft email about agents"])
    capsys.readouterr()
    rc = omw_cli.main(["history", "find", "agents"])
    hits = json.loads(capsys.readouterr().out)
    assert rc == 0 and any("agents" in h["request"] for h in hits)
    rc = omw_cli.main(["history", "list", "--outcome", "new"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0 and all(r["outcome"] == "new" for r in rows)
