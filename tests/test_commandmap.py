from scripts import commandmap
from scripts import ops_registry as reg


def test_block_lists_every_op_once():
    block = commandmap.render_block()
    for op in reg.OPS:
        assert block.count(f"`{op.name}`") >= 1, op.name
    assert commandmap.MARKER == "omw-commandmap"
    assert "<!-- omw-commandmap:start -->" in block
    assert "<!-- omw-commandmap:end -->" in block


def test_export_is_idempotent(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# AGENTS.md\n\nexisting content\n", encoding="utf-8")
    commandmap.export(tmp_path, ["codex"])
    first = target.read_text(encoding="utf-8")
    commandmap.export(tmp_path, ["codex"])
    second = target.read_text(encoding="utf-8")
    assert first == second                       # second run is a no-op diff
    assert "existing content" in second          # preserved


def test_block_marks_kind():
    block = commandmap.render_block()
    assert "procedure" in block and "run" in block   # both kinds annotated


def test_export_codex_opencode_dedup(tmp_path):
    commandmap.export(tmp_path, ["codex", "opencode"])
    agents = (tmp_path / "AGENTS.md").read_text()
    assert agents.count("<!-- omw-commandmap:start -->") == 1   # written once, not twice
    assert not (tmp_path / "CLAUDE.md").exists()
