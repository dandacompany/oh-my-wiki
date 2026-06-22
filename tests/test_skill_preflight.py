from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def test_skill_documents_cli_preflight_bootstrap():
    t = SKILL.read_text(encoding="utf-8")
    assert "bin/ensure-cli.sh" in t
    assert "OMW_BIN" in t
    # Still forbids the module form (bootstrap installs the real CLI instead).
    assert "python3 -m scripts" in t  # the existing HARD RULE remains
