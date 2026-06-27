import pytest

from scripts import persona_bundle, persona_run


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
