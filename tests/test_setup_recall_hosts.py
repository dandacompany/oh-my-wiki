"""L2: an interactive *empty* host pick must mean "no hosts" (skip all writes),
not collapse (`[] or None`) into the all-hosts default. A non-interactive run
with no host argument keeps the repo-host default."""
import sys

from scripts import setup_wizard


def _patch_writers(monkeypatch):
    """Record host-affecting writes; never touch real files."""
    from scripts import recall, commandmap, config
    from scripts import ask as ask_mod
    calls = {"upsert": [], "wire": [], "commandmap_hosts": None, "ask_hosts": None}
    monkeypatch.setattr(config, "set_config", lambda *a, **k: None)
    monkeypatch.setattr(recall, "render_recall_block", lambda mode: "BLOCK")
    monkeypatch.setattr(recall, "render_always_on_block", lambda: "ALWAYS")
    monkeypatch.setattr(recall, "upsert_block",
                        lambda path, block, **k: calls["upsert"].append(str(path)))
    monkeypatch.setattr(recall, "wire_host",
                        lambda host: (calls["wire"].append(host) or (True, "wired")))
    monkeypatch.setattr(commandmap, "export",
                        lambda base, hosts, **k: calls.__setitem__("commandmap_hosts", list(hosts)))
    monkeypatch.setattr(ask_mod, "export",
                        lambda base, hosts, **k: calls.__setitem__("ask_hosts", list(hosts)))
    monkeypatch.setattr(setup_wizard, "_normalize_admin_switch",
                        lambda db, prov, *, assume_yes: {"ok": True, "provider": prov,
                                                         "vaults_reindexed": 0, "detail": None})
    return calls


def test_interactive_empty_host_pick_writes_nothing(monkeypatch, tmp_path):
    calls = _patch_writers(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    # only the host checkbox is prompted (mode/strategy/normalizer passed in);
    # an empty checkbox selection = explicit "no hosts".
    monkeypatch.setattr(setup_wizard, "_prompt",
                        lambda kind, msg, **k: [] if kind == "checkbox" else (k.get("default")))
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", normalizer="heuristic",
                                   hosts=None, base_dir=str(tmp_path))
    assert rc == 0
    assert calls["upsert"] == []          # no instruction-block writes
    assert calls["wire"] == []            # no native hooks wired
    # empty pick → no host units → command-map export skipped entirely (the old
    # no-op call with [] was removed); "never called" (None) also means zero writes.
    assert calls["commandmap_hosts"] in (None, [])  # exported to zero hosts


def test_noninteractive_no_arg_defaults_to_repo_hosts(monkeypatch, tmp_path):
    calls = _patch_writers(monkeypatch)
    from scripts import hosts as hostsmod
    repo_hosts = {h for h, d in hostsmod.HOSTS.items() if d["kind"] == "repo"}
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", normalizer="heuristic",
                                   hosts=None, base_dir=str(tmp_path), noninteractive=True)
    assert rc == 0
    assert set(calls["commandmap_hosts"]) == repo_hosts  # repo-host default preserved


def test_recall_hermes_multi_profiles_fan_out(monkeypatch, tmp_path):
    """`profiles=[...]` injects the recall block + wires the hook into every
    selected hermes profile."""
    from pathlib import Path
    from scripts import recall
    calls = _patch_writers(monkeypatch)
    wired = []
    monkeypatch.setattr(recall, "wire_hermes",
                        lambda *, profile=None, **k: (wired.append(profile) or (True, "wired")))
    home = tmp_path / "home"
    for name in ("iris", "mark"):
        (home / ".hermes" / "profiles" / name).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", normalizer="heuristic",
                                   hosts=["hermes"], profiles=["iris", "mark"],
                                   base_dir=str(tmp_path), noninteractive=True)
    assert rc == 0
    # recall block injected into BOTH profiles' SOUL.md
    upserted = " ".join(calls["upsert"])
    assert "iris" in upserted and "mark" in upserted
    # native hook wired once per profile
    assert sorted(wired) == ["iris", "mark"]


def test_recall_hermes_honors_hermes_home(monkeypatch, tmp_path):
    calls = _patch_writers(monkeypatch)
    from scripts import recall
    monkeypatch.setattr(recall, "wire_hermes", lambda **k: (True, "wired"))
    hermes_home = tmp_path / "opt" / "data"
    (hermes_home / "profiles" / "oliver").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    rc = setup_wizard.setup_recall(
        mode="auto", strategy="fts", normalizer="heuristic",
        hosts=["hermes"], profiles=["oliver"],
        base_dir=str(tmp_path), noninteractive=True,
    )

    assert rc == 0
    assert str(hermes_home / "profiles" / "oliver" / "SOUL.md") in calls["upsert"]
