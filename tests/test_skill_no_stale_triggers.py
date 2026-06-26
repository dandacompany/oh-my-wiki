from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent / "SKILL.md"
_STALE = ("hot-cache", "vault-setup", "vault-use", "vault-list",
          "vault-forget", "vault-import-memo")


def test_skill_has_no_stale_op_names():
    text = _SKILL.read_text(encoding="utf-8")
    for dead in _STALE:
        assert dead not in text, f"SKILL.md still references stale op {dead!r}"


def test_skill_points_at_generated_triggers():
    text = _SKILL.read_text(encoding="utf-8")
    assert "omw-commandmap" in text
    assert "triggers" in text.lower()


def test_skill_has_no_handmaintained_trigger_table():
    text = _SKILL.read_text(encoding="utf-8")
    assert "## Trigger-phrase routing hint" not in text
