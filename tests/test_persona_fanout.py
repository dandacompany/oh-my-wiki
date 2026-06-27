import pathlib
import subprocess
import sys as _sys

import pytest

from scripts import persona_fanout
from tests.conftest import make_vault_with_pages


def test_resolve_explicit_pages_emits_commands():
    out = persona_fanout.resolve(
        "fact-checker", db_path="db", vault_id=1, pages=["a.md", "b.md"])
    assert out["role"] == "fact-checker"
    assert out["count"] == 2
    assert out["pages"] == ["a.md", "b.md"]
    assert out["commands"] == [
        "omw persona-run fact-checker --page a.md",
        "omw persona-run fact-checker --page b.md",
    ]


def test_resolve_explicit_pages_dedup_preserves_order():
    out = persona_fanout.resolve(
        "fact-checker", db_path="db", vault_id=1, pages=["a.md", "a.md", "b.md"])
    assert out["pages"] == ["a.md", "b.md"]


def test_resolve_backend_appended_to_commands():
    out = persona_fanout.resolve(
        "fact-checker", db_path="db", vault_id=1, pages=["a.md"], backend="codex")
    assert out["commands"] == ["omw persona-run fact-checker --page a.md --backend codex"]


def test_resolve_facet_type(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/entities/x.md": "---\ntitle: X\ntype: entity\n---\n\nbody",
        "wiki/entities/y.md": "---\ntitle: Y\ntype: entity\n---\n\nbody",
        "raw/r.md": "# raw\n",
    })
    out = persona_fanout.resolve(
        "fact-checker", db_path=db, vault_id=vid, type="entity")
    assert out["count"] == 2
    assert out["pages"] == ["wiki/entities/x.md", "wiki/entities/y.md"]
    assert all(c.startswith("omw persona-run fact-checker --page wiki/entities/")
               for c in out["commands"])


def test_resolve_zero_matches_is_clean_empty(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/r.md": "# r\n"})
    out = persona_fanout.resolve("fact-checker", db_path=db, vault_id=vid, type="entity")
    assert out["count"] == 0
    assert out["pages"] == [] and out["commands"] == []


def test_resolve_pages_and_facet_mutually_exclusive():
    with pytest.raises(persona_fanout.FanoutError, match="mutually exclusive"):
        persona_fanout.resolve("fact-checker", db_path="db", vault_id=1,
                               pages=["a.md"], type="entity")


def test_resolve_no_selector_errors():
    with pytest.raises(persona_fanout.FanoutError, match="no page selector"):
        persona_fanout.resolve("fact-checker", db_path="db", vault_id=1)


def test_resolve_rejects_vault_wide_role():
    for role in ("consistency-checker", "curator"):
        with pytest.raises(persona_fanout.FanoutError, match="vault-wide"):
            persona_fanout.resolve(role, db_path="db", vault_id=1, pages=["a.md"])


def test_resolve_rejects_unknown_role():
    with pytest.raises(persona_fanout.FanoutError, match="unknown"):
        persona_fanout.resolve("not-a-persona", db_path="db", vault_id=1, pages=["a.md"])


def test_cli_persona_fanout_explicit_pages():
    proc = subprocess.run(
        [_sys.executable, "-m", "scripts.omw_cli", "persona-fanout",
         "fact-checker", "--pages", "a.md,b.md"],
        capture_output=True, text=True,
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0
    assert "omw persona-run fact-checker --page a.md" in proc.stdout


def test_resolve_quotes_relpaths_with_spaces():
    out = persona_fanout.resolve(
        "fact-checker", db_path="db", vault_id=1, pages=["My Notes/Page One.md"])
    # the emitted command must be safe to paste into a shell
    assert out["commands"] == ["omw persona-run fact-checker --page 'My Notes/Page One.md'"]


def test_cli_persona_fanout_vault_wide_role_errors():
    proc = subprocess.run(
        [_sys.executable, "-m", "scripts.omw_cli", "persona-fanout",
         "curator", "--pages", "a.md"],
        capture_output=True, text=True,
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 1
    assert "vault-wide" in (proc.stderr + proc.stdout)
