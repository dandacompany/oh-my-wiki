import pytest

from scripts import omw_cli

SUBCOMMANDS = [
    "list", "create", "use", "forget", "info", "current",
    "rename", "move", "set", "archive", "unarchive", "delete",
]


def test_vault_help_lists_all_subcommands(capsys):
    # argparse prints help then SystemExit(0) on -h
    with pytest.raises(SystemExit):
        omw_cli.main(["vault", "-h"])
    out = capsys.readouterr().out
    for name in SUBCOMMANDS:
        assert name in out, f"`omw vault -h` is missing subcommand: {name}"


def test_ops_registry_vault_invocation_lists_new_subcommands():
    from scripts import ops_registry
    vault_op = next(o for o in ops_registry.OPS if o.name == "vault")
    for name in ["info", "current", "rename", "move", "set",
                 "archive", "unarchive", "delete"]:
        assert name in vault_op.cli_template
