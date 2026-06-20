"""omw setup wizard — non-interactive contract."""
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


def test_setup_search_brightdata_needs_key_and_zone(monkeypatch):
    from scripts import config, omw_cli
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    monkeypatch.delenv("BRIGHTDATA_ZONE", raising=False)
    omw_cli.main(["setup", "search", "--noninteractive", "--provider", "brightdata", "--api-key", "K"])
    assert config.load_config()["search"]["enabled"] is False   # zone 없음
    omw_cli.main(["setup", "search", "--noninteractive", "--provider", "brightdata", "--api-key", "K", "--zone", "Z"])
    assert config.load_config()["search"]["enabled"] is True
    assert config.read_secret("BRIGHTDATA_API_KEY") == "K" and config.read_secret("BRIGHTDATA_ZONE") == "Z"


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
    monkeypatch.setattr(setup_wizard, "setup_serve", lambda **k: calls.append("serve") or 0)
    monkeypatch.setattr(setup_wizard, "setup_personas", lambda **k: calls.append("personas") or 0)
    monkeypatch.setattr(setup_wizard, "setup_import", lambda **k: calls.append("import") or 0)
    monkeypatch.setattr(setup_wizard, "setup_viewer", lambda **k: calls.append("viewer") or 0)
    monkeypatch.setattr(setup_wizard, "setup_agents", lambda **k: calls.append("agents") or 0)
    monkeypatch.setattr(setup_wizard, "setup_recall", lambda **k: calls.append("recall") or 0)
    rc = setup_wizard.run_all(noninteractive=False, base_dir=tmp_path)
    assert rc == 0
    assert calls == ["vault", "search", "serve", "personas", "import", "viewer", "agents", "recall"]


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
    rc = sw.setup_agents(agents=["codex", "hermes"], noninteractive=True)
    assert rc == 0
    assert seen["agents"] == ["codex", "hermes"]
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
