"""Tests that setup_recall preserves existing recall config (G2 non-lossy requirement)."""
from tests.conftest import make_vault_with_pages
from scripts import setup_wizard, config


def test_setup_recall_preserves_strategy(tmp_path, monkeypatch):
    """setup_recall(noninteractive=True) must not reset recall.strategy or recall.mode
    when they have already been configured (G2: non-lossy setup_recall)."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/a.md": "# A\n\nx"})
    config.set_config("recall.mode", "advisory")
    config.set_config("recall.strategy", "hybrid")
    setup_wizard.setup_recall(noninteractive=True, base_dir=str(tmp_path))
    cfg = config.load_config().get("recall") or {}
    assert cfg.get("strategy") == "hybrid", (
        f"Expected strategy='hybrid' but got {cfg.get('strategy')!r}; "
        "setup_recall must not reset recall.strategy to its default"
    )
    assert cfg.get("mode") == "advisory", (
        f"Expected mode='advisory' but got {cfg.get('mode')!r}; "
        "setup_recall must not reset recall.mode to its default"
    )


def test_setup_recall_explicit_args_override(tmp_path, monkeypatch):
    """Explicitly passed args must still override the existing config."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/b.md": "# B\n\ny"})
    config.set_config("recall.mode", "advisory")
    config.set_config("recall.strategy", "hybrid")
    setup_wizard.setup_recall(noninteractive=True, mode="auto", strategy="fts",
                               base_dir=str(tmp_path))
    cfg = config.load_config().get("recall") or {}
    assert cfg.get("strategy") == "fts", "Explicit strategy='fts' must win over saved 'hybrid'"
    assert cfg.get("mode") == "auto", "Explicit mode='auto' must win over saved 'advisory'"


def test_setup_recall_first_run_defaults(tmp_path, monkeypatch):
    """On first run (no existing config) defaults are fts/auto as before."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/c.md": "# C\n\nz"})
    setup_wizard.setup_recall(noninteractive=True, base_dir=str(tmp_path))
    cfg = config.load_config().get("recall") or {}
    assert cfg.get("strategy") == "fts", "First-run default strategy must be 'fts'"
    assert cfg.get("mode") == "auto", "First-run default mode must be 'auto'"


def test_setup_personas_preserves_roster(tmp_path, monkeypatch):
    """setup_personas(noninteractive=True) with no args must preserve the existing
    enabled roster + main persona (G2: non-lossy setup_personas)."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/d.md": "# D\n\nw"})
    # First call: explicitly set a specific roster
    rc = setup_wizard.setup_personas(
        enabled=["wiki-librarian", "curator"],
        main="curator",
        hosts=["codex"],
        noninteractive=True,
        base_dir=str(tmp_path),
    )
    assert rc == 0, "First setup_personas call should succeed"
    # Second call: no args — must preserve the previously saved roster
    rc2 = setup_wizard.setup_personas(noninteractive=True, base_dir=str(tmp_path))
    assert rc2 == 0, "Second setup_personas call should succeed"
    cfg = config.load_config().get("personas") or {}
    assert cfg.get("enabled") == ["wiki-librarian", "curator"], (
        f"Expected enabled=['wiki-librarian','curator'] but got {cfg.get('enabled')!r}; "
        "setup_personas must not reset enabled to all personas on re-run"
    )
    assert cfg.get("main") == "curator", (
        f"Expected main='curator' but got {cfg.get('main')!r}; "
        "setup_personas must not reset main to 'wiki-librarian' on re-run"
    )


def test_setup_personas_explicit_args_override(tmp_path, monkeypatch):
    """Explicitly passed args to setup_personas must still override the existing config."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/e.md": "# E\n\nv"})
    # First call: set a specific roster
    setup_wizard.setup_personas(
        enabled=["wiki-librarian", "curator"],
        main="curator",
        hosts=["codex"],
        noninteractive=True,
        base_dir=str(tmp_path),
    )
    # Second call: explicit args should override saved config
    rc = setup_wizard.setup_personas(
        enabled=["wiki-librarian"],
        main="wiki-librarian",
        hosts=["codex"],
        noninteractive=True,
        base_dir=str(tmp_path),
    )
    assert rc == 0
    cfg = config.load_config().get("personas") or {}
    assert cfg.get("enabled") == ["wiki-librarian"], (
        "Explicit enabled=['wiki-librarian'] must override saved ['wiki-librarian','curator']"
    )
    assert cfg.get("main") == "wiki-librarian", (
        "Explicit main='wiki-librarian' must override saved 'curator'"
    )


def test_setup_personas_first_run_defaults(tmp_path, monkeypatch):
    """On first run (no existing config) default is all personas with wiki-librarian main."""
    make_vault_with_pages(tmp_path, monkeypatch, pages={"wiki/f.md": "# F\n\nu"})
    rc = setup_wizard.setup_personas(
        hosts=["codex"],
        noninteractive=True,
        base_dir=str(tmp_path),
    )
    assert rc == 0
    cfg = config.load_config().get("personas") or {}
    from scripts import personas
    all_names = [p["name"] for p in personas.list_personas()]
    assert cfg.get("enabled") == all_names, (
        f"First-run default enabled must be all personas {all_names!r}, got {cfg.get('enabled')!r}"
    )
    assert cfg.get("main") == "wiki-librarian", (
        f"First-run default main must be 'wiki-librarian', got {cfg.get('main')!r}"
    )
