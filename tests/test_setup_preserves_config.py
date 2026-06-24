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
