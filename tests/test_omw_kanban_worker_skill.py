# tests/test_omw_kanban_worker_skill.py
from pathlib import Path

from scripts import hermes_kanban


def _skill_path() -> Path:
    return Path(__file__).resolve().parents[1] / "personas" / "skills" / \
        hermes_kanban.WORKER_SKILL / "SKILL.md"


def test_worker_skill_file_exists():
    assert _skill_path().is_file()


def test_worker_skill_states_the_lifecycle_contract():
    text = _skill_path().read_text(encoding="utf-8")
    # the three lifecycle terminators + omw's propose->confirm invariant
    assert "kanban_complete" in text
    assert "kanban_block" in text
    assert "review-required" in text
    assert ".proposed.md" in text
    # destructive ops must never auto-apply
    assert "merge" in text and "supersede" in text and "delete" in text
