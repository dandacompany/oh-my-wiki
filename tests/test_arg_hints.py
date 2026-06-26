from scripts import ops_registry as reg


def test_subcommand_ops_have_clear_templates():
    # the invocation template should enumerate the subcommands so the agent sees them
    assert "{" in reg.get("history").cli_template and "log" in reg.get("history").cli_template
    assert "{" in reg.get("review").cli_template
    assert "{" in reg.get("visibility").cli_template


def test_list_op_documents_its_filter_flags():
    a = {x.name for x in reg.get("list").args}
    assert {"--tag", "--type", "--status"} <= a


def test_every_argspec_has_a_nonempty_hint():
    for op in reg.OPS:
        for arg in op.args:
            assert arg.hint and arg.hint.strip(), f"{op.name} {arg.name}: empty hint"
