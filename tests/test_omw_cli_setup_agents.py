import scripts.omw_cli as omw_cli
import scripts.agent_skills as ask


def test_cli_setup_agents_routes(monkeypatch, capsys):
    monkeypatch.setattr(ask, "detect_agents", lambda: ["codex"])
    calls = {}
    monkeypatch.setattr(ask, "install_many",
                        lambda agents, **k: calls.update({"agents": agents}) or
                        [{"agent": a, "ok": True, "method": "copy"} for a in agents])
    rc = omw_cli.main(["setup", "agents", "--agents", "codex", "--noninteractive"])
    assert rc == 0
    assert calls["agents"] == ["codex"]
