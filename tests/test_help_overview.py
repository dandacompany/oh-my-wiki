import pytest
from scripts import help_overview, ops_registry as reg


def test_render_lists_every_op_under_a_phase():
    text = help_overview.render()
    # every registered op name appears
    for op in reg.OPS:
        assert op.name in text, op.name
    # lifecycle phase headers appear in order
    for ph in ("capture", "structure", "synthesize", "retrieve", "maintain", "use"):
        assert ph in text.lower()
    # CLI vs skill tags present
    assert "[CLI]" in text and "[skill]" in text


def test_every_op_has_an_explicit_phase():
    # Assert explicit _PHASE membership, not just non-None: the `.get(name, "meta")`
    # fallback would otherwise make `op.phase` always truthy, letting a new op silently
    # land in "meta". This forces a deliberate phase choice for every registered op.
    for op in reg.OPS:
        assert op.name in reg._PHASE, f"{op.name} missing from ops_registry._PHASE map"
        assert op.phase is not None, f"{op.name} has no phase"


def test_help_registered_deterministic():
    assert reg.get("help") is not None and reg.get("help").kind == "deterministic"


def test_omw_help_command_emits_grouped_overview(capsys):
    from scripts import omw_cli
    rc = omw_cli.main(["help"])
    out = capsys.readouterr().out
    assert rc == 0
    # the grouped overview (not argparse usage) is shown
    assert "commands by lifecycle phase" in out
    assert "Capture — bring sources in" in out
    assert "[CLI]" in out and "[skill]" in out
    # NOT the flat argparse usage line
    assert "usage: omw [-h]" not in out


@pytest.mark.parametrize("argv", [["-h"], ["--help"], []])
def test_top_level_help_is_grouped_not_flat(argv, capsys):
    # -h / --help / no-args all show the lifecycle-grouped overview, NOT argparse's
    # flat one-line subcommand dump.
    from scripts import omw_cli
    rc = omw_cli.main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert "commands by lifecycle phase" in out
    assert "Capture — bring sources in" in out
    # the old flat argparse subcommand dump must be gone
    assert "usage: omw [-h]" not in out
    assert "positional arguments:" not in out
