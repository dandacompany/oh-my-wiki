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
    assert calls["commandmap_hosts"] == []  # exported to zero hosts


def test_noninteractive_no_arg_defaults_to_repo_hosts(monkeypatch, tmp_path):
    calls = _patch_writers(monkeypatch)
    from scripts import hosts as hostsmod
    repo_hosts = {h for h, d in hostsmod.HOSTS.items() if d["kind"] == "repo"}
    rc = setup_wizard.setup_recall(mode="auto", strategy="fts", normalizer="heuristic",
                                   hosts=None, base_dir=str(tmp_path), noninteractive=True)
    assert rc == 0
    assert set(calls["commandmap_hosts"]) == repo_hosts  # repo-host default preserved
