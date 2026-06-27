import pathlib
import subprocess
import sys as _sys

import pytest

from scripts import persona_bundle, persona_run
from scripts import persona_run as _pr
from tests.conftest import make_vault_with_pages

FAKES = str(pathlib.Path(__file__).resolve().parent / "fakes")


def test_needs_source_self_gathering_vs_source_driven():
    assert persona_run.needs_source("fact-checker") is True
    assert persona_run.needs_source("terminology-manager") is True
    assert persona_run.needs_source("wiki-librarian") is True
    assert persona_run.needs_source("wiki-auditor") is True
    assert persona_run.needs_source("consistency-checker") is False
    assert persona_run.needs_source("curator") is False


def test_load_bundle_unknown_name_raises():
    with pytest.raises(persona_bundle.BundleError, match="unknown bundle"):
        persona_bundle.load_bundle("does-not-exist")


def test_load_bundle_rejects_unknown_role(tmp_path, monkeypatch):
    bad = tmp_path / "bundles"
    bad.mkdir()
    (bad / "bad.yaml").write_text(
        "name: bad\ndescription: d\nroles: [consistency-checker, not-a-persona]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(persona_bundle, "BUNDLES_ROOT", bad)
    with pytest.raises(persona_bundle.BundleError, match="unknown role"):
        persona_bundle.load_bundle("bad")


def test_load_bundle_requires_roles_nonempty(tmp_path, monkeypatch):
    d = tmp_path / "bundles"
    d.mkdir()
    (d / "empty.yaml").write_text("name: empty\ndescription: d\nroles: []\n", encoding="utf-8")
    monkeypatch.setattr(persona_bundle, "BUNDLES_ROOT", d)
    with pytest.raises(persona_bundle.BundleError, match="roles"):
        persona_bundle.load_bundle("empty")


def test_shipped_tidy_bundle_loads():
    b = persona_bundle.load_bundle("tidy")
    assert b["name"] == "tidy"
    assert b["roles"] == ["consistency-checker", "curator"]


def test_list_bundles_includes_tidy_and_skips_invalid():
    names = {b["name"] for b in persona_bundle.list_bundles()}
    assert "tidy" in names


def _fake_bundle(monkeypatch, roles):
    monkeypatch.setattr(
        persona_bundle, "load_bundle",
        lambda name: {"name": name, "description": "d", "roles": list(roles)},
    )


def test_run_bundle_runs_roles_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(persona_bundle, "load_bundle",
                        lambda name: {"name": "t", "description": "d",
                                      "roles": ["consistency-checker", "curator"]})
    monkeypatch.setattr(_pr, "run", lambda role, **kw: calls.append(role) or 0)
    rc = persona_bundle.run_bundle("t", db_path="db", vault_id=1)
    assert rc == 0
    assert calls == ["consistency-checker", "curator"]


def test_run_bundle_continues_on_failure_and_exits_nonzero(monkeypatch):
    calls = []
    monkeypatch.setattr(persona_bundle, "load_bundle",
                        lambda name: {"name": "t", "description": "d",
                                      "roles": ["consistency-checker", "curator"]})

    def fake_run(role, **kw):
        calls.append(role)
        return 1 if role == "consistency-checker" else 0

    monkeypatch.setattr(_pr, "run", fake_run)
    rc = persona_bundle.run_bundle("t", db_path="db", vault_id=1)
    assert calls == ["consistency-checker", "curator"]  # continued past the failure
    assert rc == 1                                       # any failure → non-zero


def test_run_bundle_failclosed_when_source_role_without_page(monkeypatch):
    calls = []
    _fake_bundle(monkeypatch, ["fact-checker"])
    monkeypatch.setattr(_pr, "run", lambda role, **kw: calls.append(role) or 0)
    rc = persona_bundle.run_bundle("t", db_path="db", vault_id=1, page=None)
    assert rc == 1
    assert calls == []  # nothing dispatched


def test_run_bundle_passes_page_only_to_source_driven_roles(monkeypatch):
    seen = {}
    _fake_bundle(monkeypatch, ["consistency-checker", "fact-checker"])
    monkeypatch.setattr(_pr, "run",
                        lambda role, **kw: seen.__setitem__(role, kw.get("source")) or 0)
    rc = persona_bundle.run_bundle("t", db_path="db", vault_id=1, page="p.md")
    assert rc == 0
    assert seen["consistency-checker"] is None                 # self-gathering ignores page
    assert seen["fact-checker"] == {"vault_relpath": "p.md"}   # source-driven gets it


def test_run_bundle_tidy_integration_stages_index(tmp_path, monkeypatch):
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"a.md": "# A\n"})
    from scripts import registry
    index = registry.get_vault_root(db, vid) / "wiki" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setenv("OMW_BACKEND_OVERRIDE_PATH", FAKES)
    rc = persona_bundle.run_bundle("tidy", db_path=db, vault_id=vid,
                                   backend="codex", override_cli_path=FAKES)
    assert rc == 0
    assert index.read_text() == "ORIGINAL"                       # curator stages, never overwrites
    assert (index.parent / "index.md.proposed.md").exists()


def test_run_bundle_survives_role_exception(monkeypatch):
    calls = []
    monkeypatch.setattr(persona_bundle, "load_bundle",
                        lambda name: {"name": "t", "description": "d",
                                      "roles": ["consistency-checker", "curator"]})

    def fake_run(role, **kw):
        calls.append(role)
        if role == "consistency-checker":
            raise RuntimeError("boom")
        return 0

    monkeypatch.setattr(_pr, "run", fake_run)
    rc = persona_bundle.run_bundle("t", db_path="db", vault_id=1)
    assert calls == ["consistency-checker", "curator"]  # continued past the crash
    assert rc == 1


def test_load_bundle_rejects_empty_name(tmp_path, monkeypatch):
    d = tmp_path / "bundles"
    d.mkdir()
    (d / "badname.yaml").write_text(
        "name: \"\"\ndescription: d\nroles: [consistency-checker]\n", encoding="utf-8"
    )
    monkeypatch.setattr(persona_bundle, "BUNDLES_ROOT", d)
    with pytest.raises(persona_bundle.BundleError, match="name must be a non-empty string"):
        persona_bundle.load_bundle("badname")


def test_load_bundle_rejects_duplicate_keys(tmp_path, monkeypatch):
    d = tmp_path / "bundles"
    d.mkdir()
    (d / "dup.yaml").write_text(
        "name: dup\ndescription: d\nroles: [consistency-checker]\nroles: [curator]\n",
        encoding="utf-8")
    monkeypatch.setattr(persona_bundle, "BUNDLES_ROOT", d)
    with pytest.raises(persona_bundle.BundleError, match="duplicate"):
        persona_bundle.load_bundle("dup")


def test_cli_persona_bundle_list_runs():
    proc = subprocess.run(
        [_sys.executable, "-m", "scripts.omw_cli", "persona-bundle", "list"],
        capture_output=True, text=True,
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0
    assert "tidy" in proc.stdout
