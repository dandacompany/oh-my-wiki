import re
from pathlib import Path

from scripts import ops_registry as reg

_ROOT = Path(__file__).resolve().parent.parent


def test_history_card_exists_and_refs_real_ops():
    p = _ROOT / "commands" / "history.md"
    assert p.exists(), "commands/history.md should document when to log/consult"
    text = p.read_text(encoding="utf-8")
    assert "omw history log" in text and "omw history similar" in text
    for verb in re.findall(r"`omw ([a-z][a-z-]+)", text):
        assert reg.get(verb) is not None, f"history.md references unknown op: {verb}"


def test_skill_md_mentions_history():
    text = (_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "omw history" in text
