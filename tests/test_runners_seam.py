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
