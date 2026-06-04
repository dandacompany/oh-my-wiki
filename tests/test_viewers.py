import sys
from pathlib import Path

from scripts import config, registry, setup_wizard
from scripts.paths import registry_path
from scripts.viewers import base


def test_quote_value_encodes_space_slash_korean():
    assert base.quote_value("a b") == "a%20b"
    assert base.quote_value("wiki/entities/x.md") == "wiki%2Fentities%2Fx.md"
    assert base.quote_value("안드레이") == "%EC%95%88%EB%93%9C%EB%A0%88%EC%9D%B4"


def test_opener_argv_per_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert base.opener_argv() == ["open"]
    monkeypatch.setattr(sys, "platform", "linux")
    assert base.opener_argv() == ["xdg-open"]
    monkeypatch.setattr(sys, "platform", "win32")
    assert base.opener_argv()[:3] == ["cmd", "/c", "start"]


def test_launch_invokes_runner_with_uri_and_returns_it():
    calls = []
    out = base.launch("obsidian://open?vault=demo", runner=lambda argv, **kw: calls.append(argv))
    assert out == "obsidian://open?vault=demo"
    assert calls and calls[0][-1] == "obsidian://open?vault=demo"


def test_vaultref_fields():
    v = base.VaultRef(root=Path("/tmp/demo"), name="demo")
    assert v.root == Path("/tmp/demo") and v.name == "demo"


from scripts.viewers.obsidian import ObsidianViewer


def _vault(tmp_path):
    return base.VaultRef(root=tmp_path, name="demo")


def test_obsidian_open_vault(tmp_path):
    assert ObsidianViewer().open_vault(_vault(tmp_path)) == "obsidian://open?vault=demo"


def test_obsidian_open_page_uses_absolute_path(tmp_path):
    uri = ObsidianViewer().open_page(_vault(tmp_path), "wiki/entities/x.md")
    assert uri == "obsidian://open?path=" + base.quote_value(str(tmp_path / "wiki/entities/x.md"))


def test_obsidian_search(tmp_path):
    assert ObsidianViewer().search(_vault(tmp_path), "compounding knowledge") == \
        "obsidian://search?vault=demo&query=compounding%20knowledge"


def test_obsidian_scaffold_writes_core_plugins_and_app(tmp_path):
    written, hints = ObsidianViewer().scaffold_config(_vault(tmp_path))
    cp = tmp_path / ".obsidian" / "core-plugins.json"
    app = tmp_path / ".obsidian" / "app.json"
    assert cp in written and app in written
    import json
    assert "graph" in json.loads(cp.read_text())
    assert json.loads(app.read_text())["alwaysUpdateLinks"] is True
    assert any("dataview" in h.lower() for h in hints)


def test_obsidian_scaffold_is_idempotent_union(tmp_path):
    import json
    obs = ObsidianViewer()
    cp = tmp_path / ".obsidian" / "core-plugins.json"
    cp.parent.mkdir(parents=True)
    cp.write_text(json.dumps(["my-custom-plugin"]))
    obs.scaffold_config(_vault(tmp_path))
    plugins = json.loads(cp.read_text())
    assert "my-custom-plugin" in plugins and "graph" in plugins  # union, not clobber


from scripts.viewers.logseq import LogseqViewer


def test_logseq_open_vault(tmp_path):
    assert LogseqViewer().open_vault(_vault(tmp_path)) == "logseq://graph/demo"


def test_logseq_open_page_uses_stem(tmp_path):
    uri = LogseqViewer().open_page(_vault(tmp_path), "wiki/entities/andrej-karpathy.md")
    assert uri == "logseq://graph/demo?page=andrej-karpathy"


def test_logseq_search_falls_back_to_graph_and_flags_no_search(tmp_path):
    lv = LogseqViewer()
    assert lv.supports_search is False
    assert lv.search(_vault(tmp_path), "anything") == "logseq://graph/demo"


def test_logseq_scaffold_writes_config_edn_and_skips_existing(tmp_path):
    lv = LogseqViewer()
    written, _ = lv.scaffold_config(_vault(tmp_path))
    edn = tmp_path / "logseq" / "config.edn"
    assert edn in written and ":preferred-format :markdown" in edn.read_text()
    edn.write_text(";; user-edited\n")
    lv.scaffold_config(_vault(tmp_path))            # second run must not clobber
    assert edn.read_text() == ";; user-edited\n"


from scripts import viewers


def test_get_viewer_returns_right_class():
    assert viewers.get_viewer("obsidian").name == "obsidian"
    assert viewers.get_viewer("logseq").name == "logseq"


def test_get_viewer_unknown_raises():
    import pytest
    with pytest.raises(viewers.UnknownViewer):
        viewers.get_viewer("roam")


from types import SimpleNamespace
from scripts import view


def test_pick_viewer_name_default_obsidian():
    assert view.pick_viewer_name({}, None) == "obsidian"
    assert view.pick_viewer_name({"viewer": {"default": "logseq"}}, None) == "logseq"
    assert view.pick_viewer_name({"viewer": {"default": "logseq"}}, "obsidian") == "obsidian"


def test_viewer_vault_name_default_basename_and_override():
    root = Path("/tmp/my-vault")
    assert view.viewer_vault_name({}, "obsidian", root) == "my-vault"
    cfg = {"viewer": {"obsidian": {"vault_name": "Custom"}}}
    assert view.viewer_vault_name(cfg, "obsidian", root) == "Custom"


def test_resolve_page_direct_relpath(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "x.md").write_text("hi")
    assert view.resolve_page([], tmp_path, "wiki/x.md") == "wiki/x.md"


def test_resolve_page_by_stem(tmp_path):
    rows = [{"relpath": "wiki/entities/andrej-karpathy.md"}]
    assert view.resolve_page(rows, tmp_path, "andrej-karpathy") == "wiki/entities/andrej-karpathy.md"


def test_resolve_page_not_found_raises_with_candidates(tmp_path):
    import pytest
    rows = [{"relpath": "wiki/concepts/llm-wiki.md"}]
    with pytest.raises(view.PageNotFound) as ei:
        view.resolve_page(rows, tmp_path, "llm")
    assert "llm-wiki.md" in " ".join(ei.value.candidates)


def test_run_print_builds_uri_without_launching(tmp_path, monkeypatch, capsys):
    import os, subprocess
    home = tmp_path / "omw"
    env = {**os.environ, "OMW_HOME": str(home)}
    root = str(Path(view.__file__).resolve().parents[1])
    subprocess.run([sys.executable, "-m", "scripts.omw_cli", "vault", "create", "demo", "--mode", "wiki"],
                   check=True, env=env, cwd=root)
    args = SimpleNamespace(page=None, search=None, viewer=None, vault=None, print=True)
    monkeypatch.setenv("OMW_HOME", str(home))
    rc = view.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip().startswith("obsidian://open?vault=demo")


def test_setup_viewer_sets_default_and_scaffolds(tmp_path, monkeypatch):
    home = tmp_path / "omw"
    monkeypatch.setenv("OMW_HOME", str(home))
    import os, subprocess
    env = {**os.environ, "OMW_HOME": str(home)}
    subprocess.run([sys.executable, "-m", "scripts.omw_cli", "vault", "create", "demo", "--mode", "wiki"],
                   check=True, env=env, cwd=str(Path(setup_wizard.__file__).resolve().parents[1]))
    rc = setup_wizard.setup_viewer(viewer="obsidian", noninteractive=True)
    assert rc == 0
    assert (config.load_config().get("viewer") or {}).get("default") == "obsidian"
    active = registry.get_active(registry_path())
    assert (Path(active["path"]) / ".obsidian" / "core-plugins.json").is_file()


def test_cli_view_print_smoke(tmp_path):
    import os, subprocess
    home = tmp_path / "omw"
    env = {**os.environ, "OMW_HOME": str(home)}
    root = str(Path(__file__).resolve().parents[1])  # repo root (tests/ is under it)
    subprocess.run([sys.executable, "-m", "scripts.omw_cli", "vault", "create", "demo", "--mode", "wiki"],
                   check=True, env=env, cwd=root)
    r = subprocess.run([sys.executable, "-m", "scripts.omw_cli", "view", "--print"],
                       capture_output=True, text=True, env=env, cwd=root)
    assert r.returncode == 0
    assert r.stdout.strip() == "obsidian://open?vault=demo"

    r2 = subprocess.run([sys.executable, "-m", "scripts.omw_cli", "view", "--print",
                         "--viewer", "logseq", "--search", "x"],
                        capture_output=True, text=True, env=env, cwd=root)
    assert r2.returncode == 0
    assert r2.stdout.strip() == "logseq://graph/demo"


def test_run_launch_failure_is_graceful(tmp_path, monkeypatch, capsys):
    import os, subprocess
    home = tmp_path / "omw"
    env = {**os.environ, "OMW_HOME": str(home)}
    root = str(Path(view.__file__).resolve().parents[1])
    subprocess.run([sys.executable, "-m", "scripts.omw_cli", "vault", "create", "demo", "--mode", "wiki"],
                   check=True, env=env, cwd=root)
    monkeypatch.setenv("OMW_HOME", str(home))

    def boom(uri, **kw):
        raise FileNotFoundError("xdg-open")
    monkeypatch.setattr(view, "launch", boom)
    args = SimpleNamespace(page=None, search=None, viewer=None, vault=None, print=False)
    rc = view.run(args)
    err = capsys.readouterr().err
    assert rc == 0
    assert "obsidian://open?vault=demo" in err  # URI still surfaced, no crash


def test_run_invalid_configured_viewer_errors(tmp_path, monkeypatch):
    import os, subprocess
    home = tmp_path / "omw"
    env = {**os.environ, "OMW_HOME": str(home)}
    root = str(Path(view.__file__).resolve().parents[1])
    subprocess.run([sys.executable, "-m", "scripts.omw_cli", "vault", "create", "demo", "--mode", "wiki"],
                   check=True, env=env, cwd=root)
    monkeypatch.setenv("OMW_HOME", str(home))
    monkeypatch.setattr(view.config, "load_config", lambda: {"viewer": {"default": "roam"}})
    args = SimpleNamespace(page=None, search=None, viewer=None, vault=None, print=True)
    assert view.run(args) == 1


def test_obsidian_scaffold_enables_navigation_plugins(tmp_path):
    from scripts.viewers.obsidian import ObsidianViewer
    from scripts.viewers.base import VaultRef
    import json
    ref = VaultRef(root=tmp_path, name=tmp_path.name)
    ObsidianViewer().scaffold_config(ref)
    cp = json.loads((tmp_path / ".obsidian" / "core-plugins.json").read_text())
    for plugin in ("file-explorer", "switcher", "command-palette"):
        assert plugin in cp, f"{plugin} missing — vault would be unbrowsable in Obsidian"
