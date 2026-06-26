import re

from scripts import commandmap


def test_block_has_triggers_column_and_keywords():
    block = commandmap.render_block()
    # header gains a triggers column
    assert "| op | kind | invocation | what it does | triggers |" in block
    # a routable op's keyword appears in its row
    assert "현황" in block       # report
    assert "이력" in block       # history
    # block is deterministic (stable across calls)
    assert block == commandmap.render_block()


def test_allowlisted_op_has_empty_triggers_cell():
    block = commandmap.render_block()
    # the status row exists and ends with an empty triggers cell
    status_line = next(ln for ln in block.splitlines() if ln.startswith("| `status` |"))
    assert status_line.rstrip().endswith("|  |") or status_line.rstrip().endswith("| |")


def test_every_row_is_five_columns():
    block = commandmap.render_block()
    body = [ln for ln in block.splitlines()
            if ln.startswith("| `")]            # body rows only (skip header/separator)
    assert body, "no body rows found"
    for ln in body:
        # split on pipes not preceded by a backslash; a well-formed 5-col row → 7 segments
        cells = re.split(r"(?<!\\)\|", ln)
        assert len(cells) == 7, f"row not 5 columns: {ln!r} -> {len(cells)-2} cells"
    # spot-check a subcommand op's triggers keyword is intact in the row, not split out
    vault_line = next(ln for ln in body if ln.startswith("| `vault` |"))
    assert "볼트" in vault_line
