import os
import pathlib
import pytest
from scripts import persona_run

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
