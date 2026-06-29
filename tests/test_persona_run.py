import os
import pathlib
import pytest
from scripts import persona_run
from scripts import personas

FAKES = str(pathlib.Path(__file__).resolve().parent / "fakes")


def test_pick_backend_prefers_requested_then_first_authed():
    detected = {
        "claude": {"installed": True, "authed": True},
        "codex": {"installed": True, "authed": False},
    }
    assert persona_run._pick_backend(detected, "claude") == "claude"
    assert persona_run._pick_backend(detected, None) == "claude"
    with pytest.raises(persona_run.RunError):
        persona_run._pick_backend({"codex": {"installed": True, "authed": False}}, None)


def test_dispatch_runs_fake_backend_and_returns_stdout(monkeypatch):
    out = persona_run._dispatch(
        "You are a tester.", "Say hello.",
        backend="codex", model="fake-model", override_cli_path=FAKES,
    )
    assert isinstance(out, str) and out  # fake echoes something non-empty


def test_dispatch_raises_on_backend_failure():
    with pytest.raises(persona_run.RunError):
        os.environ["OMW_FAKE_FAIL"] = "1"
        try:
            persona_run._dispatch("b", "t", backend="codex", model="m",
                                  override_cli_path=FAKES)
        finally:
            os.environ.pop("OMW_FAKE_FAIL", None)


def test_dispatch_closes_stdin(monkeypatch):
    import subprocess
    captured = {}

    class _CP:
        returncode = 0
        stdout = "out"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured.update(kwargs)
        return _CP()

    monkeypatch.setattr(persona_run.subprocess, "run", fake_run)
    out = persona_run._dispatch("body", "task", backend="codex", model="m",
                                override_cli_path=None)
    assert out == "out"
    assert captured.get("stdin") == subprocess.DEVNULL


# ---------------------------------------------------------------------------
# _gather_inputs tests
# ---------------------------------------------------------------------------
from tests.conftest import make_vault_with_pages  # noqa: E402


def test_gather_consistency_uses_contradiction_candidates(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "a.md": "# A\n\nThe sky is blue.",
        "b.md": "# B\n\nThe sky is green.",
    })
    task, meta = persona_run._gather_inputs("consistency-checker", db_path=db, vault_id=vid)
    assert "contradiction" in task.lower() or "candidate" in task.lower()
    assert isinstance(meta, dict)


def test_gather_curator_uses_index_drift(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "orphan.md": "# Orphan\n\nnot in index.",
    })
    task, meta = persona_run._gather_inputs("curator", db_path=db, vault_id=vid)
    assert "index" in task.lower()


def test_gather_factcheck_uses_source(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"p.md": "# P\n\nClaim X."})
    task, meta = persona_run._gather_inputs(
        "fact-checker", db_path=db, vault_id=vid, source={"vault_relpath": "p.md"})
    assert "claim" in task.lower()


def test_gather_wiki_auditor_self_gathers(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nbody"})
    task, meta = persona_run._gather_inputs("wiki-auditor", db_path=db, vault_id=vid)
    assert meta == {}
    assert "lint" in task and "broken_links" in task   # no --page needed


def test_gather_wiki_librarian_self_gathers(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nbody"})
    task, meta = persona_run._gather_inputs("wiki-librarian", db_path=db, vault_id=vid)
    assert meta == {}
    assert "graph" in task and "orphans" in task


def test_needs_source_after_self_gather_change():
    assert persona_run.needs_source("wiki-auditor") is False
    assert persona_run.needs_source("wiki-librarian") is False
    assert persona_run.needs_source("consistency-checker") is False
    assert persona_run.needs_source("curator") is False
    assert persona_run.needs_source("fact-checker") is True
    assert persona_run.needs_source("terminology-manager") is True


# ---------------------------------------------------------------------------
# Filing tests: additive direct and mutation staged
# ---------------------------------------------------------------------------

def test_additive_output_filed_directly(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"p.md": "# P\n\nClaim."})
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("fact-checker", db_path=db, vault_id=vid,
                         source={"vault_relpath": "p.md"}, backend="codex",
                         override_cli_path=FAKES)
    assert rc == 0
    # fact-checker output_kind is sibling_suffix → a sibling report exists
    sib = list((tmp_path).rglob("*.factcheck.md"))
    assert sib, "additive sibling report should be filed directly"


def test_mutation_staged_not_applied(tmp_path):
    target = tmp_path / "index.md"
    target.write_text("ORIGINAL", encoding="utf-8")
    prop = persona_run._stage_proposal(target, "PROPOSED")
    assert prop.exists() and prop.read_text() == "PROPOSED"
    assert target.read_text() == "ORIGINAL"  # never auto-applied
    out = persona_run.apply_proposal(prop)
    assert out == target and target.read_text() == "PROPOSED"
    assert not prop.exists()


def test_cli_persona_run_files_report(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"p.md": "# P\n\nClaim."})
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    from scripts import omw_cli
    rc = omw_cli.main(["persona-run", "fact-checker", "--page", "p.md", "--backend", "codex"])
    assert rc == 0
    assert list(tmp_path.rglob("*.factcheck.md")), "CLI persona-run should file the sibling report"


def test_curator_propose_still_stages(tmp_path, monkeypatch):
    """Regression: curator (access=propose) stages index.md, never overwrites it."""
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"a.md": "# A\n"})
    from scripts import registry
    index = registry.get_vault_root(db, vid) / "wiki" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("ORIGINAL INDEX", encoding="utf-8")
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("curator", db_path=db, vault_id=vid,
                         backend="codex", override_cli_path=FAKES)
    assert rc == 0
    assert index.read_text() == "ORIGINAL INDEX"  # never auto-applied
    assert (index.parent / "index.md.proposed.md").exists()


def test_propose_access_generalizes_beyond_curator(tmp_path, monkeypatch):
    """A non-curator persona with access=propose + inplace stages onto its source page."""
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"p.md": "# P\n\nbody"})
    from scripts import registry
    page = registry.get_vault_root(db, vid) / "p.md"
    synthetic = {
        "name": "shaper", "description": "x", "capabilities": [], "tools": [],
        "model_hint": "standard", "input_kinds": ["vault_page"],
        "output_kind": "inplace", "access": "propose", "body": "You reshape pages.",
    }
    monkeypatch.setattr(personas, "load_persona", lambda name: synthetic)
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("shaper", db_path=db, vault_id=vid,
                         source={"vault_relpath": "p.md"}, backend="codex",
                         override_cli_path=FAKES)
    assert rc == 0
    assert page.read_text() == "# P\n\nbody"  # source untouched
    assert (page.parent / "p.md.proposed.md").exists()  # staged, not written inplace


def test_mutation_roles_symbol_removed():
    """The hardcoded mutation set is gone — access drives staging now."""
    assert not hasattr(persona_run, "_MUTATION_ROLES")


# ---------------------------------------------------------------------------
# Codex model-unsupported fallback tests
# ---------------------------------------------------------------------------

def test_dispatch_codex_falls_back_when_model_unsupported(monkeypatch):
    calls = []

    class _CP:
        def __init__(self, rc, out):
            self.returncode = rc
            self.stdout = out
            self.stderr = ""

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if "--model" in argv:
            return _CP(1, "ERROR: The 'gpt-5' model is not supported when using Codex ...")
        return _CP(0, "FALLBACK_OK")

    monkeypatch.setattr(persona_run.subprocess, "run", fake_run)
    out = persona_run._dispatch("body", "task", backend="codex", model="gpt-5",
                                override_cli_path=None)
    assert out == "FALLBACK_OK"
    assert len(calls) == 2                      # tried with model, then retried without
    assert "--model" in calls[0] and "--model" not in calls[1]


def test_dispatch_no_fallback_for_non_model_errors(monkeypatch):
    calls = []

    class _CP:
        def __init__(self, rc, out):
            self.returncode = rc
            self.stdout = out
            self.stderr = "boom"

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _CP(1, "some other error")

    monkeypatch.setattr(persona_run.subprocess, "run", fake_run)
    with pytest.raises(persona_run.RunError):
        persona_run._dispatch("body", "task", backend="codex", model="gpt-5",
                              override_cli_path=None)
    assert len(calls) == 1                       # no retry on unrelated errors


def test_dispatch_no_model_fallback_for_non_codex(monkeypatch):
    calls = []

    class _CP:
        def __init__(self, rc, out):
            self.returncode = rc
            self.stdout = out
            self.stderr = ""

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _CP(1, "the 'X' model is not supported")

    monkeypatch.setattr(persona_run.subprocess, "run", fake_run)
    with pytest.raises(persona_run.RunError):
        persona_run._dispatch("body", "task", backend="claude", model="m",
                              override_cli_path=None)
    assert len(calls) == 1   # non-codex never retries, even on a model-unsupported message


# ---------------------------------------------------------------------------
# Phase 1: empty-output is a loud failure; stdout personas emit their body
# ---------------------------------------------------------------------------

def test_dispatch_raises_on_empty_rc0_output(monkeypatch):
    """rc==0 but blank stdout is a failure, not a silent success."""
    class _CP:
        returncode = 0
        stdout = "   \n\t "
        stderr = ""

    monkeypatch.setattr(persona_run.subprocess, "run", lambda argv, **k: _CP())
    with pytest.raises(persona_run.RunError, match="empty output"):
        persona_run._dispatch("body", "task", backend="codex", model="m",
                              override_cli_path=None)


def test_run_stdout_persona_emits_body_to_stdout(tmp_path, monkeypatch, capsys):
    """A read-only/stdout persona (wiki-librarian) prints its body to stdout
    instead of dropping it; the machine receipt goes to stderr."""
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"a.md": "# A\n\nbody"})
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("wiki-librarian", db_path=db, vault_id=vid,
                         backend="codex", override_cli_path=FAKES)
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out.strip(), "stdout persona must emit its body on stdout"
    assert '"kind": "stdout"' in cap.err   # receipt on stderr, not stdout
    assert '"kind"' not in cap.out         # stdout is the body, not the JSON receipt


def test_run_warns_when_inside_host_but_slides_to_other_backend(tmp_path, monkeypatch, capsys):
    """Inside the claude host but only codex is usable → dispatch slides to codex;
    must warn loudly (the 'personas look broken in <host>' root cause)."""
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"a.md": "# A\n\nbody"})
    monkeypatch.setattr(persona_run.host_detect, "current_host", lambda: "claude")
    monkeypatch.setattr(persona_run.backends, "detect_available",
                        lambda **k: {"codex": {"installed": True, "authed": True}})
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("wiki-librarian", db_path=db, vault_id=vid,
                         backend=None, override_cli_path=FAKES)
    assert rc == 0
    err = capsys.readouterr().err
    assert "running inside the 'claude' host" in err
    assert "omw links suggest" in err   # role-specific deterministic fallback hint


def test_run_failure_includes_fallback_hint(tmp_path, monkeypatch, capsys):
    """A dispatch failure surfaces the role's deterministic fallback, not a dead end."""
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"a.md": "# A\n\nbody"})
    monkeypatch.setattr(persona_run, "_dispatch",
                        lambda *a, **k: (_ for _ in ()).throw(persona_run.RunError("boom")))
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_run.run("wiki-librarian", db_path=db, vault_id=vid,
                         backend="codex", override_cli_path=FAKES)
    assert rc == 1
    assert "fallback" in capsys.readouterr().err
