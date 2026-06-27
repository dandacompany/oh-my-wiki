import sys

from scripts import setup_wizard, agent_skills, hosts


def test_picker_offers_all_six_hosts(monkeypatch, capsys):
    # Only claude/codex detected; picker must still OFFER all six.
    monkeypatch.setattr(agent_skills, "detect_agents", lambda: ["claude", "codex"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    seen = {}

    def fake_prompt(kind, msg, *, choices=None, default=None):
        seen["choices"] = list(choices or [])
        return []  # user picks nothing

    monkeypatch.setattr(setup_wizard, "_prompt", fake_prompt)
    monkeypatch.setattr(agent_skills, "install_many", lambda a: [])
    setup_wizard.setup_agents()
    bare = {c.split(" (")[0] for c in seen["choices"]}
    assert bare == set(hosts.HOSTS.keys())              # all six offered
    # undetected scoped hosts carry a configure hint
    labels = " ".join(seen["choices"])
    assert "hermes (" in labels and "openclaw (" in labels


def test_selecting_undetected_scoped_host_installs_nothing(monkeypatch, capsys):
    monkeypatch.setattr(agent_skills, "detect_agents", lambda: ["claude"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(setup_wizard, "_prompt",
                        lambda kind, msg, **k: ["openclaw (--workspace)"])
    called = {"install": False}
    monkeypatch.setattr(agent_skills, "install_many",
                        lambda a: called.__setitem__("install", True) or [])
    rc = setup_wizard.setup_agents()
    out = capsys.readouterr().out
    assert called["install"] is False          # nothing installed
    assert "openclaw" in out and "--workspace" in out  # configure hint shown
    assert rc == 0
