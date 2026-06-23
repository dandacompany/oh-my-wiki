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


import re
from pathlib import Path
from scripts import omw_cli

_ROOT = Path(__file__).resolve().parent.parent


def test_cli_agentic_ops_match_registry_procedures():
    assert set(omw_cli.AGENTIC_OPS) == set(reg.procedures())


def test_recall_hook_verbs_are_registered_deterministic():
    text = (_ROOT / "scripts" / "recall.py").read_text(encoding="utf-8")
    for verb in re.findall(r"omw ([a-z][a-z-]+) \"", text):
        spec = reg.get(verb)
        assert spec is not None, f"recall hint references unknown op: {verb}"
        assert spec.kind == "deterministic", f"recall hint points at a procedure: {verb}"


def test_no_dangling_op_references():
    known = set(reg.names())
    # Tokens after "omw" in prose/headings that are NOT op names.
    # Keep this list minimal — add only non-op English words caught by the regex.
    allow = {
        "team",          # leftover substring guard (belt-and-suspenders)
        "deliberately",  # SKILL.md prose: "omw deliberately does not ship its own runtime"
        "has",           # SKILL.md prose: "omw has exactly two ways to run things"
        "stays",         # SKILL.md prose: "omw stays focused on the wiki"
        "without",       # SKILL.md/menu.md prose: "opens omw without a specific verb"
        "maintenance",   # gate.py module docstring: "omw maintenance gate"
        "wiki",          # gate.py display label: "omw wiki upkeep gate"
        "menu",          # commands/menu.md heading: "# omw menu — interactive entry point"
                         # (menu is the bare-invocation handler, not a registered op)
        "op",            # SKILL.md command-map prose: "omw <op> --help shows one op's args"
    }
    sources = [
        _ROOT / "SKILL.md",
        _ROOT / "scripts" / "gate.py",
        *(_ROOT / "commands").glob("*.md"),
    ]
    bad = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for verb in re.findall(r"omw ([a-z][a-z-]+)", text):
            if verb not in known and verb not in allow:
                bad.append(f"{path.name}: omw {verb}")
    assert not bad, f"dangling op references: {sorted(set(bad))}"
