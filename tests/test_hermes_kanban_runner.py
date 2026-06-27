# tests/test_hermes_kanban_runner.py
import json
import stat
from pathlib import Path

import pytest

from scripts.runners import hermes_kanban as hkr


@pytest.fixture
def fake_hermes(tmp_path):
    """A fake `hermes` CLI: appends its argv (JSON) to calls.log and prints
    a JSON task object with an incrementing id."""
    log = tmp_path / "calls.log"
    counter = tmp_path / "counter"
    counter.write_text("0")
    script = tmp_path / "hermes"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, pathlib\n"
        f"log = pathlib.Path({str(log)!r})\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "argv = sys.argv[1:]\n"
        "with log.open('a') as f: f.write(json.dumps(argv) + '\\n')\n"
        "n = int(counter.read_text()) + 1\n"
        "counter.write_text(str(n))\n"
        "print(json.dumps({'id': f't-{n:03d}', 'status': 'ready'}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {"cli": str(script), "log": log}


@pytest.fixture
def stub_builders(monkeypatch):
    monkeypatch.setattr(
        "scripts.hermes_kanban.build_card_body",
        lambda role, *, db_path, vault_id, source=None: f"BODY:{role}:{(source or {}).get('vault_relpath')}",
    )


def _logged_calls(log: Path):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_run_one_creates_one_ready_card(monkeypatch, fake_hermes, stub_builders):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    r = hkr.HermesKanbanRunner()
    out = r.run_one("fact-checker", db_path="db", vault_id=1,
                    source={"vault_relpath": "p.md"},
                    override_cli_path=fake_hermes["cli"])
    assert out["cards"] == ["t-001"]
    calls = _logged_calls(fake_hermes["log"])
    assert len(calls) == 1
    argv = calls[0]
    assert argv[:2] == ["kanban", "create"]
    assert argv[argv.index("--assignee") + 1] == "sophie"
    assert argv[argv.index("--skill") + 1] == "omw-kanban-worker"
    assert "--parent" not in argv  # single card has no parents


def test_fanout_creates_one_card_per_page(monkeypatch, fake_hermes, stub_builders):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    monkeypatch.setattr(
        "scripts.persona_fanout.resolve",
        lambda role, **kw: {"role": role, "backend": None, "count": 2,
                            "pages": ["a.md", "b.md"], "commands": []},
    )
    r = hkr.HermesKanbanRunner()
    out = r.resolve_fanout("fact-checker", db_path="db", vault_id=1,
                           pages=["a.md", "b.md"],
                           override_cli_path=fake_hermes["cli"])
    assert out["count"] == 2
    assert out["cards"] == ["t-001", "t-002"]
    calls = _logged_calls(fake_hermes["log"])
    assert len(calls) == 2
    for argv in calls:
        assert "--parent" not in argv  # fanout cards are independent/parallel


def test_bundle_chains_parents_in_order(monkeypatch, fake_hermes, stub_builders):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    monkeypatch.setattr(
        "scripts.persona_bundle.load_bundle",
        lambda name: {"name": name, "description": "d",
                      "roles": ["fact-checker", "consistency-checker"]},
    )
    r = hkr.HermesKanbanRunner()
    out = r.run_bundle("wiki-team", db_path="db", vault_id=1, page="p.md",
                       override_cli_path=fake_hermes["cli"])
    assert out["cards"] == ["t-001", "t-002"]
    calls = _logged_calls(fake_hermes["log"])
    assert len(calls) == 2
    # first card: no parent; second card: parent is the first card's id
    assert "--parent" not in calls[0]
    assert calls[1][calls[1].index("--parent") + 1] == "t-001"


def test_run_one_ambiguous_profile_propagates(monkeypatch, fake_hermes, stub_builders, tmp_path):
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hh"))
    for n in ("a", "b"):
        d = tmp_path / "hh" / "profiles" / n
        d.mkdir(parents=True)
        (d / "config.yaml").write_text("model: x\n")
    from scripts.hermes_detect import AmbiguousProfile
    r = hkr.HermesKanbanRunner()
    with pytest.raises(AmbiguousProfile):
        r.run_one("fact-checker", db_path="db", vault_id=1,
                  source={"vault_relpath": "p.md"},
                  override_cli_path=fake_hermes["cli"])


def test_create_card_raises_on_cli_failure(monkeypatch, tmp_path, stub_builders):
    monkeypatch.setenv("HERMES_PROFILE", "sophie")
    bad = tmp_path / "hermes"
    bad.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(3)\n")
    bad.chmod(bad.stat().st_mode | stat.S_IEXEC)
    r = hkr.HermesKanbanRunner()
    with pytest.raises(hkr.KanbanError):
        r.run_one("fact-checker", db_path="db", vault_id=1,
                  source={"vault_relpath": "p.md"},
                  override_cli_path=str(bad))
