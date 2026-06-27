"""Tests for --runner flag routing on persona CLI ops."""
import pytest

from scripts import omw_cli


def _parse(argv):
    parser = omw_cli.build_parser()
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Basic brief tests (from task-5-brief.md)
# ---------------------------------------------------------------------------

def test_persona_run_has_runner_flag_default_host():
    ns = _parse(["persona-run", "fact-checker", "--page", "p.md"])
    assert ns.runner == "host"


def test_persona_run_accepts_hermes_kanban():
    ns = _parse(["persona-run", "fact-checker", "--page", "p.md",
                 "--runner", "hermes-kanban"])
    assert ns.runner == "hermes-kanban"


def test_persona_run_rejects_unknown_runner():
    with pytest.raises(SystemExit):
        _parse(["persona-run", "fact-checker", "--runner", "bogus"])


def test_kanban_runner_outside_hermes_errors(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    ns = _parse(["persona-run", "fact-checker", "--page", "p.md",
                 "--runner", "hermes-kanban"])
    # Route should detect the gate and exit non-zero with a clear message,
    # without dispatching anything.
    from unittest.mock import patch
    fake_vault = {"id": "fake-vault-id"}
    with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
        with patch("scripts.omw_cli._require_vault_row", return_value=fake_vault):
            rc = ns.func(ns)
    assert rc != 0
    assert "Hermes" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Runner flag parsing tests
# ---------------------------------------------------------------------------

class TestRunnerFlagParsing:
    def test_runner_flag_on_persona_run(self):
        for choice in ("host", "hermes-kanban", "hermes-delegate"):
            ns = _parse(["persona-run", "wiki-librarian", "--runner", choice])
            assert ns.runner == choice

    def test_runner_flag_on_persona_bundle_run(self):
        for choice in ("host", "hermes-kanban", "hermes-delegate"):
            ns = _parse(["persona-bundle", "run", "my-bundle", "--runner", choice])
            assert ns.runner == choice

    def test_runner_flag_on_persona_fanout(self):
        for choice in ("host", "hermes-kanban", "hermes-delegate"):
            ns = _parse(["persona-fanout", "wiki-librarian", "--pages", "A", "--runner", choice])
            assert ns.runner == choice

    def test_default_runner_is_host_everywhere(self):
        for argv in [
            ["persona-run", "wiki-librarian"],
            ["persona-bundle", "run", "my-bundle"],
            ["persona-fanout", "wiki-librarian", "--pages", "A"],
        ]:
            ns = _parse(argv)
            assert ns.runner == "host"

    def test_assignee_flag_in_parser(self):
        for argv in [
            ["persona-run", "wiki-librarian", "--assignee", "alice"],
            ["persona-bundle", "run", "my-bundle", "--assignee", "bob"],
            ["persona-fanout", "wiki-librarian", "--pages", "A", "--assignee", "carol"],
        ]:
            ns = _parse(argv)
            assert ns.assignee is not None

    def test_assignee_default_is_none(self):
        for argv in [
            ["persona-run", "wiki-librarian"],
            ["persona-bundle", "run", "my-bundle"],
            ["persona-fanout", "wiki-librarian", "--pages", "A"],
        ]:
            ns = _parse(argv)
            assert ns.assignee is None

    def test_runner_flag_in_parser(self):
        """All three persona subparsers accept --runner."""
        for cmd in [
            ["persona-run", "wiki-librarian", "--runner", "host"],
            ["persona-bundle", "run", "my-bundle", "--runner", "hermes-kanban"],
            ["persona-fanout", "wiki-librarian", "--pages", "A", "--runner", "hermes-delegate"],
        ]:
            ns = _parse(cmd)
            assert ns.runner in ("host", "hermes-kanban", "hermes-delegate")


# ---------------------------------------------------------------------------
# Routing behavior tests
# ---------------------------------------------------------------------------

class TestPersonaRunRouting:
    def _call(self, argv, monkeypatch, extra_patches=None):
        """Parse argv, patch vault resolution, call the handler, return (rc, out, err)."""
        import io
        from unittest.mock import patch

        ns = _parse(argv)
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        fake_vault = {"id": "fake-vault-id"}
        patches = [
            patch("scripts.omw_cli.registry_path", return_value="/fake/db"),
            patch("scripts.omw_cli._require_vault_row", return_value=fake_vault),
        ]
        if extra_patches:
            patches.extend(extra_patches)

        for p in patches:
            p.__enter__()
        try:
            with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
                rc = ns.func(ns)
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

        return rc, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_host_default_calls_persona_run(self, monkeypatch):
        monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
        monkeypatch.delenv("HERMES_PROFILE", raising=False)
        from unittest.mock import patch, MagicMock
        mock_run = MagicMock(return_value=0)
        with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
            with patch("scripts.omw_cli._require_vault_row", return_value={"id": "fv"}):
                with patch("scripts.persona_run.run", mock_run):
                    ns = _parse(["persona-run", "wiki-librarian", "--page", "MyPage"])
                    rc = ns.func(ns)
        mock_run.assert_called_once()
        # host route returns whatever persona_run.run returns
        assert rc == 0

    def test_hermes_kanban_no_session_exits_nonzero(self, monkeypatch, capsys):
        monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
        monkeypatch.delenv("HERMES_PROFILE", raising=False)
        ns = _parse(["persona-run", "wiki-librarian", "--page", "P",
                     "--runner", "hermes-kanban"])
        from unittest.mock import patch
        with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
            with patch("scripts.omw_cli._require_vault_row", return_value={"id": "fv"}):
                rc = ns.func(ns)
        assert rc != 0
        captured = capsys.readouterr()
        assert "Hermes" in captured.err or "hermes" in captured.err.lower()

    def test_hermes_delegate_persona_run_prints_card(self, capsys):
        ns = _parse(["persona-run", "wiki-librarian", "--page", "MyPage",
                     "--runner", "hermes-delegate"])
        from unittest.mock import patch
        with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
            with patch("scripts.omw_cli._require_vault_row", return_value={"id": "fv"}):
                rc = ns.func(ns)
        out = capsys.readouterr().out
        assert rc == 0
        assert "runner-hermes-delegate" in out
        assert "wiki-librarian" in out
        assert "commands/runner-hermes-delegate.md" in out

    def test_hermes_delegate_persona_bundle_errors(self, capsys):
        ns = _parse(["persona-bundle", "run", "some-bundle",
                     "--runner", "hermes-delegate"])
        from unittest.mock import patch
        with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
            with patch("scripts.omw_cli._require_vault_row", return_value={"id": "fv"}):
                rc = ns.func(ns)
        assert rc == 2
        err = capsys.readouterr().err
        assert "hermes-delegate" in err or "persona-run" in err

    def test_hermes_delegate_persona_fanout_errors(self, capsys):
        ns = _parse(["persona-fanout", "wiki-librarian", "--pages", "A,B",
                     "--runner", "hermes-delegate"])
        from unittest.mock import patch
        with patch("scripts.omw_cli.registry_path", return_value="/fake/db"):
            with patch("scripts.omw_cli._require_vault_row", return_value={"id": "fv"}):
                rc = ns.func(ns)
        assert rc == 2
        err = capsys.readouterr().err
        assert "hermes-delegate" in err or "persona-run" in err
