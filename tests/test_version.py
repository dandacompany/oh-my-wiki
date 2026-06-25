from scripts import banner, omw_cli, ops_registry as reg


def _expected() -> str:
    return f"omw {banner.version()}"


def test_omw_version_subcommand(capsys):
    rc = omw_cli.main(["version"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == _expected()


def test_omw_dash_v(capsys):
    rc = omw_cli.main(["-v"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == _expected()


def test_omw_dash_dash_version(capsys):
    rc = omw_cli.main(["--version"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == _expected()


def test_version_op_registered_deterministic():
    op = reg.get("version")
    assert op is not None and op.kind == "deterministic"
    assert "version" not in reg.procedures()
    # SSOT: must carry an explicit lifecycle phase (the strengthened phase test guards this)
    assert "version" in reg._PHASE
