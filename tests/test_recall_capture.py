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


def test_as_bool_normalizes_hand_edited_values():
    assert recall._as_bool(True) is True
    assert recall._as_bool(False) is False
    assert recall._as_bool("on") is True
    assert recall._as_bool("off") is False       # the trap: non-empty string is truthy in Python
    assert recall._as_bool("garbage") is False
    assert recall._as_bool(None) is False
    assert recall._as_bool(1) is True


def test_cfg_reads_capture_toggle(monkeypatch):
    import scripts.config as cfgmod
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda: {"recall": {"capture": "on"}})
    assert recall._cfg()["capture"] is True
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda: {"recall": {"capture": "off"}})
    assert recall._cfg()["capture"] is False
    monkeypatch.setattr(cfgmod, "load_config", lambda: {"recall": {}})
    assert recall._cfg()["capture"] is False     # absent = off
    # hand-edited garbage must not raise and must be off
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda: {"recall": {"capture": ["nonsense"]}})
    assert recall._cfg()["capture"] is False
