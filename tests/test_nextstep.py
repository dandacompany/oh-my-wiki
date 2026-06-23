from scripts import nextstep


def _sig(**kw):
    base = {"raw": 0, "entities": 0, "concepts": 0, "syntheses": 0,
            "lint_issues": 0, "stale": 0, "expired": 0, "markers": [], "clusters": 0}
    base.update(kw)
    return base


def test_structure_when_raw_unstructured():
    out = nextstep.suggest(_sig(raw=10))
    assert out[0]["phase"] == "structure"


def test_synthesize_when_structured_with_clusters():
    out = nextstep.suggest(_sig(entities=5, concepts=3, syntheses=0, clusters=4))
    assert out[0]["phase"] == "synthesize"


def test_maintain_outranks_structure():
    out = nextstep.suggest(_sig(raw=10, lint_issues=3))
    assert out[0]["phase"] == "maintain"


def test_review_present_when_stale():
    out = nextstep.suggest(_sig(entities=2, syntheses=1, stale=2))
    assert any(s["phase"] == "review" for s in out)


def test_recall_is_floor_for_healthy_vault():
    out = nextstep.suggest(_sig(entities=5, concepts=5, syntheses=2))
    assert out[-1]["phase"] == "recall"
    assert out  # never empty


def test_research_marker_yields_collect():
    out = nextstep.suggest(_sig(markers=["research"]))
    assert any(s["phase"] == "collect" for s in out)


import json

from scripts import omw_cli


def test_cli_next_json_ranked(tmp_path, monkeypatch, capsys):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "raw/a.md": "# A\n\nsome collected source text about widgets.",
    })
    rc = omw_cli.main(["next", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and isinstance(out, list) and out
    assert all("phase" in s and "command" in s for s in out)


def test_cli_next_readonly_gate(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    from scripts import gate
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    before = gate.state_path().read_text(encoding="utf-8") if gate.state_path().exists() else None
    omw_cli.main(["next", "--json"])
    after = gate.state_path().read_text(encoding="utf-8") if gate.state_path().exists() else None
    assert before == after  # omw next must not mutate gate state
