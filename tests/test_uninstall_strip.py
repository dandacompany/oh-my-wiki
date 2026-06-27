from scripts import uninstall


def test_markers_are_sourced_from_modules():
    from scripts import ask, persona_export, recall, commandmap
    assert set(uninstall.MARKERS) == {
        persona_export.MARKER, recall.MARKER, recall.ALWAYS_ON_MARKER, commandmap.MARKER,
        ask.MARKER}


def test_strip_removes_block_preserves_surrounding():
    text = ("# My CLAUDE.md\n\nuser content above.\n\n"
            "<!-- omw-recall:start -->\n## omw wiki recall (managed)\n\nblock body\n"
            "<!-- omw-recall:end -->\n\nuser content below.\n")
    out, removed = uninstall.strip_marker_block(text, "omw-recall")
    assert removed is True
    assert "omw-recall" not in out
    assert "block body" not in out
    assert "user content above." in out
    assert "user content below." in out
    assert out.endswith("\n")
    assert "\n\n\n" not in out  # seam collapsed


def test_strip_absent_marker_is_noop():
    text = "# CLAUDE.md\n\njust user content.\n"
    out, removed = uninstall.strip_marker_block(text, "omw-recall")
    assert removed is False
    assert out == text


def test_strip_block_at_eof_no_trailing_garbage():
    text = "user.\n\n<!-- omw-personas:start -->\nblk\n<!-- omw-personas:end -->\n"
    out, removed = uninstall.strip_marker_block(text, "omw-personas")
    assert removed is True
    assert out == "user.\n"


def test_strip_only_block_yields_empty():
    text = "<!-- omw-commandmap:start -->\nx\n<!-- omw-commandmap:end -->\n"
    out, removed = uninstall.strip_marker_block(text, "omw-commandmap")
    assert removed is True
    assert out == ""
