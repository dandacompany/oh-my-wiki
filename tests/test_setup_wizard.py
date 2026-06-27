"""omw setup wizard — non-interactive contract."""
import sys

import pytest
import yaml

from scripts import omw_cli, registry
from scripts.paths import omw_home, registry_path


def test_noninteractive_setup_creates_vault_and_config(capsys):
    rc = omw_cli.main([
        "setup", "--noninteractive",
        "--name", "first", "--mode", "wiki", "--type", "markdown", "--location", "global",
    ])
    assert rc == 0
    vaults = registry.list_vaults(registry_path())
    assert [v["name"] for v in vaults] == ["first"]
    cfg = omw_home() / "config.yaml"
    assert cfg.is_file()
    data = yaml.safe_load(cfg.read_text())
    assert data["default_vault"] == "first" and data["version"] == 1


def test_noninteractive_setup_idempotent(capsys):
    omw_cli.main(["setup", "--noninteractive", "--name", "first"])
    rc = omw_cli.main(["setup", "--noninteractive", "--name", "first"])  # re-run
    assert rc == 0
    assert len(registry.list_vaults(registry_path())) == 1


def test_doctor_reports_state(capsys):
    omw_cli.main(["setup", "--noninteractive", "--name", "first"])
    rc = omw_cli.main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "registry" in out.lower() and "first" in out


def test_setup_search_noninteractive_writes_config_and_secret(monkeypatch):
    from scripts import config, omw_cli
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    rc = omw_cli.main(["setup", "search", "--noninteractive",
                       "--provider", "brave", "--api-key", "sk-1"])
    assert rc == 0
    assert config.load_config()["search"]["provider"] == "brave"
    assert config.load_config()["search"]["enabled"] is True
    assert config.read_secret("BRAVE_API_KEY") == "sk-1"


def test_setup_search_defer_records_disabled(monkeypatch):
    from scripts import config, omw_cli
    rc = omw_cli.main(["setup", "search", "--noninteractive", "--provider", "tavily"])
    assert rc == 0
    cfg = config.load_config()
    assert cfg["search"]["provider"] == "tavily" and cfg["search"]["enabled"] is False


def test_setup_search_brightdata_manual_zone_overrides(monkeypatch):
    """An explicit --zone is written verbatim and skips zone auto-detection."""
    from scripts import config, omw_cli
    from scripts.search.providers import brightdata
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    # Detection must NOT be consulted when --zone is given.
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: (_ for _ in ()).throw(AssertionError("should not list")))
    omw_cli.main(["setup", "search", "--noninteractive", "--provider", "brightdata",
                  "--api-key", "K", "--zone", "Z"])
    assert config.load_config()["search"]["enabled"] is True
    assert config.read_secret("BRIGHTDATA_API_KEY") == "K"
    assert config.read_secret("BRIGHTDATA_ZONE") == "Z"


def test_setup_search_brightdata_autodetects_zone_from_key(monkeypatch):
    """Key-only setup resolves a zone via the Account Management API (no --zone needed)."""
    from scripts import config, omw_cli
    from scripts.search.providers import brightdata
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    monkeypatch.setattr(brightdata, "list_zones",
                        lambda key: [{"name": "auto_serp", "type": "serp"}])
    omw_cli.main(["setup", "search", "--noninteractive", "--provider", "brightdata", "--api-key", "K"])
    assert config.load_config()["search"]["enabled"] is True
    assert config.read_secret("BRIGHTDATA_ZONE") == "auto_serp"


def test_vault_setup_preserves_search_config(monkeypatch):
    from scripts import config, omw_cli
    omw_cli.main(["setup", "search", "--noninteractive", "--provider", "brave", "--api-key", "k"])
    omw_cli.main(["setup", "--noninteractive", "--name", "v1"])
    cfg = config.load_config()
    assert cfg["search"]["provider"] == "brave" and cfg["default_vault"] == "v1"


def test_setup_serve_with_token_writes_env():
    from scripts import setup_wizard, config
    from scripts.paths import omw_home
    rc = setup_wizard.setup_serve(token="abc123")
    assert rc == 0
    assert config.read_secret("OMW_SERVE_TOKEN") == "abc123"
    mode = (omw_home() / ".env").stat().st_mode & 0o777
    assert mode == 0o600


def test_setup_serve_generate_token_writes_random():
    from scripts import setup_wizard, config
    rc = setup_wizard.setup_serve(generate_token=True)
    assert rc == 0
    tok = config.read_secret("OMW_SERVE_TOKEN")
    assert tok and len(tok) >= 20


def test_setup_serve_without_token_or_flag_errors(capsys):
    from scripts import setup_wizard
    rc = setup_wizard.setup_serve()
    assert rc == 1
    assert "token" in capsys.readouterr().err.lower()


def test_setup_personas_records_config_and_exports(tmp_path):
    from scripts import setup_wizard, config, persona_export
    rc = setup_wizard.setup_personas(
        enabled=["fact-checker", "curator"], main="fact-checker",
        hosts=["claude", "codex", "gemini"], base_dir=tmp_path,
    )
    assert rc == 0
    cfg = config.load_config()
    assert cfg["personas"]["enabled"] == ["fact-checker", "curator"]
    assert cfg["personas"]["main"] == "fact-checker"
    for f in persona_export.HOST_FILES.values():
        assert "<!-- omw-personas:start -->" in (tmp_path / f).read_text()


def test_setup_personas_unknown_name_errors(tmp_path, capsys):
    from scripts import setup_wizard
    rc = setup_wizard.setup_personas(enabled=["nonesuch"], base_dir=tmp_path)
    assert rc == 1
    assert "nonesuch" in capsys.readouterr().err


def test_setup_personas_defaults_main_to_librarian(tmp_path):
    from scripts import setup_wizard, config
    rc = setup_wizard.setup_personas(base_dir=tmp_path, hosts=["claude"])
    assert rc == 0
    assert config.load_config()["personas"]["main"] == "wiki-librarian"


def _fake_input(answers):
    """Return an input() replacement that pops scripted answers in order."""
    seq = list(answers)
    def _inp(prompt=""):
        return seq.pop(0)
    return _inp


@pytest.mark.skipif(not sys.stdin.isatty(), reason="interactive prompt requires a TTY")
def test_setup_serve_interactive_prompts_for_token(monkeypatch):
    from scripts import setup_wizard, config
    from scripts.paths import omw_home
    monkeypatch.delenv("OMW_SERVE_TOKEN", raising=False)
    monkeypatch.setattr(setup_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", _fake_input(["n", "pasted-token-123"]))
    rc = setup_wizard.setup_serve()
    assert rc == 0
    assert config.read_secret("OMW_SERVE_TOKEN") == "pasted-token-123"
    assert (omw_home() / ".env").stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(not sys.stdin.isatty(), reason="interactive prompt requires a TTY")
def test_setup_serve_interactive_generate(monkeypatch):
    from scripts import setup_wizard, config
    monkeypatch.delenv("OMW_SERVE_TOKEN", raising=False)
    monkeypatch.setattr(setup_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", _fake_input(["y"]))
    rc = setup_wizard.setup_serve()
    assert rc == 0
    tok = config.read_secret("OMW_SERVE_TOKEN")
    assert tok and len(tok) >= 20


def test_setup_serve_noninteractive_flag_unchanged(monkeypatch):
    from scripts import setup_wizard, config
    monkeypatch.delenv("OMW_SERVE_TOKEN", raising=False)
    rc = setup_wizard.setup_serve(token="flagtok", noninteractive=True)
    assert rc == 0
    assert config.read_secret("OMW_SERVE_TOKEN") == "flagtok"


@pytest.mark.skipif(not sys.stdin.isatty(), reason="interactive prompt requires a TTY")
def test_setup_personas_interactive_selects_roster(monkeypatch, tmp_path):
    from scripts import setup_wizard, config
    monkeypatch.setattr(setup_wizard.sys.stdin, "isatty", lambda: True)
    # checkbox(enabled) -> "fact-checker,curator"; select(main) -> "curator"; checkbox(hosts) -> "claude"
    monkeypatch.setattr("builtins.input",
                        _fake_input(["fact-checker,curator", "curator", "claude"]))
    rc = setup_wizard.setup_personas(base_dir=tmp_path)  # no enable/main/host flags
    assert rc == 0
    cfg = config.load_config()
    assert cfg["personas"]["enabled"] == ["fact-checker", "curator"]
    assert cfg["personas"]["main"] == "curator"
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()  # only claude host selected


def test_setup_personas_noninteractive_flags_unchanged(tmp_path):
    from scripts import setup_wizard, config
    rc = setup_wizard.setup_personas(enabled=["fact-checker"], main="fact-checker",
                                     hosts=["claude"], base_dir=tmp_path, noninteractive=True)
    assert rc == 0
    assert config.load_config()["personas"]["main"] == "fact-checker"


def test_run_all_invokes_sections_in_order(monkeypatch, tmp_path):
    from scripts import setup_wizard
    calls = []
    monkeypatch.setattr(setup_wizard, "run", lambda **k: calls.append("vault") or 0)
    monkeypatch.setattr(setup_wizard, "setup_search", lambda **k: calls.append("search") or 0)
    monkeypatch.setattr(setup_wizard, "setup_fetch", lambda **k: calls.append("fetch") or 0)
    monkeypatch.setattr(setup_wizard, "setup_serve", lambda **k: calls.append("serve") or 0)
    monkeypatch.setattr(setup_wizard, "setup_personas", lambda **k: calls.append("personas") or 0)
    monkeypatch.setattr(setup_wizard, "setup_import", lambda **k: calls.append("import") or 0)
    monkeypatch.setattr(setup_wizard, "setup_viewer", lambda **k: calls.append("viewer") or 0)
    monkeypatch.setattr(setup_wizard, "setup_agents", lambda **k: calls.append("agents") or 0)
    monkeypatch.setattr(setup_wizard, "setup_recall", lambda **k: calls.append("recall") or 0)
    rc = setup_wizard.run_all(noninteractive=False, base_dir=tmp_path)
    assert rc == 0
    # fetch comes right after search (it backs search's cloud-escalation tier)
    assert calls == ["vault", "search", "fetch", "serve", "personas",
                     "import", "viewer", "agents", "recall"]


def test_run_all_returns_first_nonzero_but_continues(monkeypatch, tmp_path):
    from scripts import setup_wizard
    calls = []
    monkeypatch.setattr(setup_wizard, "run", lambda **k: calls.append("vault") or 0)
    monkeypatch.setattr(setup_wizard, "setup_search", lambda **k: calls.append("search") or 2)
    monkeypatch.setattr(setup_wizard, "setup_serve", lambda **k: calls.append("serve") or 0)
    monkeypatch.setattr(setup_wizard, "setup_personas", lambda **k: calls.append("personas") or 0)
    monkeypatch.setattr(setup_wizard, "setup_import", lambda **k: calls.append("import") or 0)
    monkeypatch.setattr(setup_wizard, "setup_viewer", lambda **k: calls.append("viewer") or 0)
    monkeypatch.setattr(setup_wizard, "setup_agents", lambda **k: calls.append("agents") or 0)
    monkeypatch.setattr(setup_wizard, "setup_recall", lambda **k: calls.append("recall") or 0)
    rc = setup_wizard.run_all(noninteractive=False, base_dir=tmp_path)
    assert rc == 2
    assert calls == ["vault", "search", "serve", "personas", "import", "viewer", "agents", "recall"]


@pytest.mark.skipif(not sys.stdin.isatty(), reason="interactive prompt requires a TTY")
def test_setup_import_interactive_stores_notion_key(monkeypatch):
    from scripts import setup_wizard, config
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    monkeypatch.setattr(setup_wizard.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", _fake_input(["nkey-123", "~/notes"]))
    rc = setup_wizard.setup_import()
    assert rc == 0
    assert config.read_secret("NOTION_API_KEY") == "nkey-123"
    assert config.load_config()["import"]["default_src"] == "~/notes"


def test_prompt_password_fallback_uses_getpass(monkeypatch):
    import builtins, getpass, scripts.setup_wizard as sw
    real_import = builtins.__import__
    def no_questionary(name, *a, **k):
        if name == "questionary":
            raise ImportError("no questionary")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_questionary)
    called = {}
    monkeypatch.setattr(getpass, "getpass", lambda msg="": called.update({"msg": msg}) or "secret-x")
    monkeypatch.setattr(builtins, "input", lambda *a: (_ for _ in ()).throw(AssertionError("input() leaks secret")))
    assert sw._prompt("password", "API key") == "secret-x"
    assert "API key" in called["msg"]


def test_setup_agents_noninteractive_installs_detected(monkeypatch, capsys):
    import scripts.setup_wizard as sw
    import scripts.agent_skills as ask
    monkeypatch.setattr(ask, "detect_agents", lambda: ["codex", "hermes"])
    seen = {}
    monkeypatch.setattr(ask, "install_many",
                        lambda agents, **k: seen.update({"agents": agents}) or
                        [{"agent": a, "ok": True, "method": "copy"} for a in agents])
    # hermes is now routed through _install_hermes_profiles (per-profile), not install_many;
    # mock hermes_profile_targets so the test stays hermetic.
    monkeypatch.setattr(ask, "hermes_profile_targets",
                        lambda hermes_home=None: [{"name": "main", "skills_dir": None, "installed": True}])
    monkeypatch.setattr(ask, "install_into_dir",
                        lambda skills_dir, **k: {"ok": True, "method": "copy", "dest": "/fake/path", "detail": None})
    rc = sw.setup_agents(agents=["codex", "hermes"], noninteractive=True)
    assert rc == 0
    # hermes is now handled by _install_hermes_profiles; only non-hermes agents go to install_many
    assert seen["agents"] == ["codex"]
    out = capsys.readouterr().out
    assert "codex" in out and "hermes" in out


def test_setup_agents_skips_uninstalled(monkeypatch, capsys):
    import scripts.setup_wizard as sw
    import scripts.agent_skills as ask
    monkeypatch.setattr(ask, "detect_agents", lambda: ["codex"])
    monkeypatch.setattr(ask, "install_many",
                        lambda agents, **k: [{"agent": a, "ok": True, "method": "copy"} for a in agents])
    rc = sw.setup_agents(agents=["codex", "gemini"], noninteractive=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "gemini" in out and "skipped" in out


def test_recall_embedding_config_written():
    from scripts import setup_wizard, config
    setup_wizard.configure_recall(strategy="hybrid", provider="openai",
                                  model="text-embedding-3-small", dim=1536,
                                  noninteractive=True)
    cfg = config.load_config()["recall"]
    assert cfg["strategy"] == "hybrid"
    assert cfg["embedding"]["provider"] == "openai"


def test_setup_recall_persists_embedding_provider(tmp_path):
    from scripts import setup_wizard, config
    rc = setup_wizard.setup_recall(mode="auto", strategy="hybrid", submode=None,
                                   provider="openai", model="text-embedding-3-small", dim=1536,
                                   hosts=[], base_dir=str(tmp_path), noninteractive=True)
    assert rc == 0
    cfg = config.load_config()["recall"]
    assert cfg["strategy"] == "hybrid" and cfg["embedding"]["provider"] == "openai" and cfg["embedding"]["dim"] == 1536


def test_setup_recall_llm_persists_submode(tmp_path):
    from scripts import setup_wizard, config
    rc = setup_wizard.setup_recall(mode="advisory", strategy="llm", submode="generative",
                                   hosts=[], base_dir=str(tmp_path), noninteractive=True)
    assert rc == 0
    cfg = config.load_config()["recall"]
    assert cfg["strategy"] == "llm" and cfg["llm"]["submode"] == "generative"


def _wsl_prompt_router(answers, calls):
    """Build a fake _prompt that answers by message prefix and records calls."""
    def fake(kind, message, **kw):
        calls.append(message)
        for prefix, val in answers.items():
            if message.startswith(prefix):
                return val
        return None
    return fake


def test_run_interactive_wsl_windows_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts import setup_wizard, platform_env
    import pathlib
    monkeypatch.setattr(platform_env, "is_wsl", lambda: True)
    monkeypatch.setattr(platform_env, "windows_user_profile",
                        lambda: pathlib.Path("/mnt/c/Users/dante"))
    captured = {}
    monkeypatch.setattr(setup_wizard, "_ensure_vault",
                        lambda name, mode, type_, location: captured.update(
                            name=name, location=location))
    monkeypatch.setattr(setup_wizard, "_write_config", lambda v: None)
    calls = []
    monkeypatch.setattr(setup_wizard, "_prompt", _wsl_prompt_router({
        "Vault name": "myvault", "Mode": "wiki", "Type": "markdown",
        "WSL detected": "Windows drive (open in Windows Obsidian)",
    }, calls))  # no "Location" answer — it must never be asked (asserted below)
    rc = setup_wizard._run_interactive("default", "wiki", "markdown", "global",
                                       in_wizard=True)
    assert rc == 0
    assert captured["location"] == "/mnt/c/Users/dante/omw-vaults/myvault"
    assert any(m.startswith("WSL detected") for m in calls)
    assert not any(m.startswith("Location") for m in calls)   # skipped for Windows path


def test_run_interactive_wsl_fallback_when_no_winprofile(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts import setup_wizard, platform_env
    monkeypatch.setattr(platform_env, "is_wsl", lambda: True)
    monkeypatch.setattr(platform_env, "windows_user_profile", lambda: None)
    captured = {}
    monkeypatch.setattr(setup_wizard, "_ensure_vault",
                        lambda name, mode, type_, location: captured.update(location=location))
    monkeypatch.setattr(setup_wizard, "_write_config", lambda v: None)
    calls = []
    monkeypatch.setattr(setup_wizard, "_prompt", _wsl_prompt_router({
        "Vault name": "v", "Mode": "wiki", "Type": "markdown",
        "WSL detected": "Windows drive (open in Windows Obsidian)",
        "Location": "global",
    }, calls))
    rc = setup_wizard._run_interactive("default", "wiki", "markdown", "global", in_wizard=True)
    assert rc == 0
    assert any(m.startswith("Location") for m in calls)   # fell back to Location prompt
    assert captured["location"] == "global"


def test_run_interactive_non_wsl_no_wsl_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts import setup_wizard, platform_env
    monkeypatch.setattr(platform_env, "is_wsl", lambda: False)
    monkeypatch.setattr(setup_wizard, "_ensure_vault", lambda *a, **k: None)
    monkeypatch.setattr(setup_wizard, "_write_config", lambda v: None)
    calls = []
    monkeypatch.setattr(setup_wizard, "_prompt", _wsl_prompt_router({
        "Vault name": "v", "Mode": "wiki", "Type": "markdown", "Location": "global",
    }, calls))
    rc = setup_wizard._run_interactive("default", "wiki", "markdown", "global", in_wizard=True)
    assert rc == 0
    assert not any(m.startswith("WSL detected") for m in calls)   # no WSL prompt off-WSL
    assert any(m.startswith("Location") for m in calls)


def test_ensure_vault_activates_preexisting(tmp_path, monkeypatch):
    monkeypatch.setenv("OMW_HOME", str(tmp_path / ".omw"))
    from scripts import setup_wizard, registry
    from scripts.paths import registry_path
    db = registry_path()
    setup_wizard._ensure_vault("alpha", "wiki", "markdown", "global")
    setup_wizard._ensure_vault("beta", "wiki", "markdown", "global")
    assert registry.get_active(db)["name"] == "beta"        # newest active
    # re-running on the PRE-EXISTING 'alpha' must re-activate it (the bug: it didn't)
    setup_wizard._ensure_vault("alpha", "wiki", "markdown", "global")
    assert registry.get_active(db)["name"] == "alpha"
    assert sum(1 for v in registry.list_vaults(db) if v["name"] == "alpha") == 1  # no duplicate
