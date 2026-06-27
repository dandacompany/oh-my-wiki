from scripts import setup_wizard


def _trip_wire(monkeypatch):
    """Make any real write fail the test if called."""
    from scripts import recall, commandmap, config, agent_skills, persona_export
    from scripts import ask as ask_mod

    def boom(*a, **k):
        raise AssertionError("dry-run must not write")

    monkeypatch.setattr(config, "set_config", boom)
    monkeypatch.setattr(recall, "upsert_block", boom)
    monkeypatch.setattr(recall, "wire_host", boom)
    monkeypatch.setattr(recall, "wire_hermes", boom)
    monkeypatch.setattr(recall, "wire_ts_plugin", boom)
    monkeypatch.setattr(commandmap, "export", boom)
    monkeypatch.setattr(ask_mod, "export", boom)
    monkeypatch.setattr(agent_skills, "install_many", boom)
    monkeypatch.setattr(persona_export, "export_personas", boom)
    monkeypatch.setattr(
        setup_wizard,
        "_normalize_admin_switch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run")),
    )
    monkeypatch.setattr(
        setup_wizard,
        "_embed_admin_switch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run")),
    )


def test_recall_dry_run_writes_nothing(monkeypatch, capsys, tmp_path):
    _trip_wire(monkeypatch)
    rc = setup_wizard.setup_recall(
        mode="auto",
        strategy="fts",
        normalizer="heuristic",
        hosts=["claude"],
        base_dir=str(tmp_path),
        noninteractive=True,
        dry_run=True,
    )
    assert rc == 0
    assert "would" in capsys.readouterr().out.lower()


def test_agents_dry_run_writes_nothing(monkeypatch, capsys):
    from scripts import agent_skills

    monkeypatch.setattr(agent_skills, "detect_agents", lambda: ["claude"])
    _trip_wire(monkeypatch)
    rc = setup_wizard.setup_agents(agents=["claude"], noninteractive=True, dry_run=True)
    assert rc == 0
    assert "would" in capsys.readouterr().out.lower()


def test_personas_dry_run_writes_nothing(monkeypatch, capsys, tmp_path):
    _trip_wire(monkeypatch)
    rc = setup_wizard.setup_personas(
        enabled=["wiki-librarian"],
        main="wiki-librarian",
        hosts=["claude"],
        base_dir=str(tmp_path),
        noninteractive=True,
        dry_run=True,
    )
    assert rc == 0
    assert "would" in capsys.readouterr().out.lower()


def test_recall_embedding_dry_run_writes_nothing(monkeypatch, capsys, tmp_path):
    _trip_wire(monkeypatch)
    rc = setup_wizard.setup_recall(
        mode="auto",
        strategy="embedding",
        normalizer="heuristic",
        hosts=["claude"],
        base_dir=str(tmp_path),
        noninteractive=True,
        dry_run=True,
    )
    assert rc == 0
    assert "would" in capsys.readouterr().out.lower()
