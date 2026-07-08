"""Unit tests for the mem0-like per-prompt capture cue in scripts.recall."""
from scripts import recall


def test_render_capture_cue_shape():
    cue = recall.render_capture_cue()
    assert recall.CAPTURE_MARKER == "omw-capture"
    assert f"<{recall.CAPTURE_MARKER}>" in cue and f"</{recall.CAPTURE_MARKER}>" in cue
    # routes into existing machinery, not a new mechanism
    assert "omw ingest" in cue
    assert "gate note ingest" in cue
    assert "duplicate-ingest" in cue
    # write-signal framing, and an explicit "ignore if irrelevant" escape hatch
    assert "저장 신호" in cue
    assert "무관하면" in cue
