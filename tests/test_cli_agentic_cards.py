import json
from scripts import omw_cli


def _run(argv, capsys):
    rc = omw_cli.main(argv)
    return rc, capsys.readouterr().out


def test_autoresearch_binds_args_and_prints_card(capsys):
    rc, out = _run(["autoresearch", "국내 중년 남성 패션", "--rounds", "4"], capsys)
    assert rc == 0
    assert "procedure: autoresearch" in out
    assert "topic: 국내 중년 남성 패션" in out
    assert "rounds: 4" in out


def test_procedure_json_flag(capsys):
    rc, out = _run(["query", "무신사 전략?", "--json"], capsys)
    assert rc == 0
    data = json.loads(out)
    assert data["procedure"] == "query"
    assert data["args"]["question"] == "무신사 전략?"


def test_missing_optional_positional_still_cards(capsys):
    # persona-consistency's page is optional -> no hard failure
    rc, out = _run(["persona-consistency"], capsys)
    assert rc == 0
    assert "procedure: persona-consistency" in out


def test_autoresearch_no_synthesis_card_names_collect_only_mode(capsys):
    rc, out = _run(["autoresearch", "국내 중년 남성 패션", "--no-synthesis"], capsys)
    assert rc == 0
    assert "procedure: autoresearch" in out
    assert "no-synthesis: True" in out
    assert "mode: collect raw only" in out
    assert "do not call file-back" in out
