from scripts import omw_cli


def test_setup_recall_dry_run_flag_threads(monkeypatch):
    captured = {}
    from scripts import setup_wizard
    monkeypatch.setattr(setup_wizard, "setup_recall",
                        lambda **kw: captured.update(kw) or 0)
    rc = omw_cli.main(["setup", "recall", "--noninteractive", "--dry-run", "--host", "claude"])
    assert rc == 0
    assert captured.get("dry_run") is True
