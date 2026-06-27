from pathlib import Path


def _card_path() -> Path:
    return Path(__file__).resolve().parents[1] / "commands" / "runner-hermes-delegate.md"


def test_delegate_card_exists():
    assert _card_path().is_file()


def test_delegate_card_names_delegate_task_and_no_profile():
    text = _card_path().read_text(encoding="utf-8")
    assert "delegate_task" in text
    # makes clear omw cannot call the tool itself; the host must
    assert "goal" in text and "context" in text
    # secondary path: no durable board / blocked gate (set expectations)
    assert "kanban" in text  # references that kanban is the durable alternative
