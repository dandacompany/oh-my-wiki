import pytest
from scripts import ops_registry as reg


def test_every_op_is_wellformed():
    for op in reg.OPS:
        assert op.kind in ("deterministic", "procedure"), op.name
        if op.kind == "procedure":
            assert op.procedure_file, f"{op.name} procedure missing procedure_file"
            assert op.cli_template is None, f"{op.name} procedure must not set cli_template"
        else:
            assert op.procedure_file is None, f"{op.name} deterministic must not set procedure_file"
        for a in op.args:
            assert a.name and a.hint, op.name


def test_find_is_deterministic_not_procedure():
    assert reg.get("find").kind == "deterministic"
    assert "find" not in reg.procedures()


def test_team_run_is_not_registered():
    assert reg.get("team-run") is None
    assert "team-run" not in reg.names()


def test_procedures_match_expected_agentic_set():
    assert set(reg.procedures()) == {
        "ingest", "query", "open", "edit", "move", "delete", "autoresearch",
        "persona-factcheck", "persona-consistency", "persona-terminology",
    }


def test_autoresearch_args():
    a = {x.name: x for x in reg.get("autoresearch").args}
    assert a["topic"].required is True
    assert "--rounds" in a
    assert reg.get("autoresearch").uses == ("search", "fetch", "reindex")
