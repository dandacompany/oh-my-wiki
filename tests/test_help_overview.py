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


def test_every_op_has_a_phase():
    for op in reg.OPS:
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
