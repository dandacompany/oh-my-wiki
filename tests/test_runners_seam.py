import pytest

from scripts import runners


def test_available_runners_host_only_outside_hermes(monkeypatch):
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    assert runners.available_runners() == ["host"]


def test_available_runners_adds_kanban_in_hermes(monkeypatch):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    assert runners.available_runners() == ["host", "hermes-kanban"]


def test_resolve_runner_default_is_host(monkeypatch):
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    r = runners.resolve_runner(None)
    assert r.name == "host"
    assert runners.resolve_runner("host").name == "host"


def test_resolve_runner_kanban_gated_outside_hermes(monkeypatch):
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    with pytest.raises(runners.RunnerUnavailable):
        runners.resolve_runner("hermes-kanban")


def test_resolve_runner_unknown_raises():
    with pytest.raises(ValueError):
        runners.resolve_runner("nope")


def test_host_runner_run_one_delegates(monkeypatch):
    calls = {}

    def fake_run(role, **kw):
        calls["role"] = role
        calls.update(kw)
        return 0

    monkeypatch.setattr("scripts.persona_run.run", fake_run)
    r = runners.resolve_runner("host")
    rc = r.run_one("fact-checker", db_path="db", vault_id=1,
                   source={"vault_relpath": "p.md"}, backend="codex")
    assert rc == 0
    assert calls["role"] == "fact-checker"
    assert calls["backend"] == "codex"


# ---------------------------------------------------------------------------
# Phase 2: host-native dispatch — emit a procedure card instead of external spawn
# ---------------------------------------------------------------------------

def test_host_runner_emits_card_when_inside_host(monkeypatch, capsys):
    """No --backend + a detected host → emit a card; NO external dispatch."""
    monkeypatch.setattr("scripts.host_detect.current_host", lambda: "claude")
    monkeypatch.setattr("scripts.persona_run.build_host_card",
                        lambda role, **kw: "<omw-persona-card>CARD</omw-persona-card>")
    ran = {"external": False}
    monkeypatch.setattr("scripts.persona_run.run",
                        lambda *a, **k: ran.update(external=True) or 0)
    rc = runners.resolve_runner("host").run_one(
        "wiki-librarian", db_path="db", vault_id=1, source=None, backend=None)
    assert rc == 0
    assert "omw-persona-card" in capsys.readouterr().out
    assert ran["external"] is False   # host-native, no sibling-CLI spawn


def test_host_runner_external_when_backend_pinned(monkeypatch):
    """An explicit --backend keeps the external path even inside a host."""
    monkeypatch.setattr("scripts.host_detect.current_host", lambda: "claude")
    ran = {"external": False}
    monkeypatch.setattr("scripts.persona_run.run",
                        lambda *a, **k: ran.update(external=True) or 0)
    rc = runners.resolve_runner("host").run_one(
        "fact-checker", db_path="db", vault_id=1, source=None, backend="codex")
    assert rc == 0 and ran["external"] is True


def test_host_runner_external_when_no_host(monkeypatch):
    """No host detected → fall back to external dispatch."""
    monkeypatch.setattr("scripts.host_detect.current_host", lambda: None)
    ran = {"external": False}
    monkeypatch.setattr("scripts.persona_run.run",
                        lambda *a, **k: ran.update(external=True) or 0)
    runners.resolve_runner("host").run_one(
        "fact-checker", db_path="db", vault_id=1, source=None, backend=None)
    assert ran["external"] is True


def test_host_runner_apply_skips_card(monkeypatch):
    """--apply is a filing op, not a dispatch — never a host-native card."""
    monkeypatch.setattr("scripts.host_detect.current_host", lambda: "claude")
    ran = {"external": False}
    monkeypatch.setattr("scripts.persona_run.run",
                        lambda *a, **k: ran.update(external=True) or 0)
    runners.resolve_runner("host").run_one(
        "curator", db_path="db", vault_id=1, source=None, backend=None, apply=True)
    assert ran["external"] is True
