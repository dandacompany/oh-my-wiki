from scripts import ops_registry as reg


def test_subcommand_ops_enumerate_subcommands():
    # ops whose CLI dispatches on a subcommand must show the {a|b|c} set in their template
    subcommand_ops = ["vault", "inbox", "review", "schema", "visibility", "links", "gate", "history"]
    for name in subcommand_ops:
        tmpl = reg.get(name).cli_template
        assert "{" in tmpl and "}" in tmpl, f"{name} template hides its subcommands: {tmpl!r}"


def test_setup_template_lists_sections():
    tmpl = reg.get("setup").cli_template
    for section in ("vault", "personas", "recall", "search"):
        assert section in tmpl, f"setup template omits section {section!r}: {tmpl!r}"


def test_list_op_documents_its_filter_flags():
    a = {x.name for x in reg.get("list").args}
    assert {"--tag", "--type", "--status"} <= a


def test_every_argspec_has_a_nonempty_hint():
    for op in reg.OPS:
        for arg in op.args:
            assert arg.hint and arg.hint.strip(), f"{op.name} {arg.name}: empty hint"
