"""Unit tests for the mem0-like per-prompt capture cue in scripts.recall."""
import pytest

from scripts import recall


@pytest.fixture(autouse=True)
def _assume_active_vault(monkeypatch):
    # Capture is ON by default and gated on an active vault existing. These unit tests
    # run without a real registry, so assume a vault exists; the no-vault case has its
    # own test that overrides this.
    monkeypatch.setattr(recall, "_has_active_vault", lambda: True)


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
    assert recall._cfg()["capture"] is True      # absent = on (default)
    # hand-edited garbage must not raise and must be off (invalid value, not the default)
    monkeypatch.setattr(cfgmod, "load_config",
                        lambda: {"recall": {"capture": ["nonsense"]}})
    assert recall._cfg()["capture"] is False


def _cfg(**over):
    base = {"mode": "auto", "strategy": "fts", "llm_submode": "route",
            "min_score": 1.0, "top_k": 3, "snippet_chars": 280, "capture": False}
    base.update(over)
    return base


def test_capture_off_is_unchanged_auto_miss_silent(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(capture=False))
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: [])   # FTS miss
    assert recall.prompt("수요예측 파이프라인 설계 원칙이 뭐였지") == ""


def test_capture_on_emits_cue_on_auto_miss(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(capture=True))
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: [])   # FTS miss → recall body empty
    out = recall.prompt("수요예측 파이프라인 설계 원칙이 뭐였지")
    assert out == recall.render_capture_cue()                  # cue alone


def test_capture_on_trivial_still_silent(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(capture=True))
    assert recall.prompt("ok") == ""
    assert recall.prompt("네") == ""


def test_capture_on_mode_off_emits_cue_alone(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(mode="off", capture=True))
    out = recall.prompt("우리 프로젝트는 파이썬 3.10 stdlib만 쓴다")
    assert out == recall.render_capture_cue()


def test_capture_off_mode_off_still_silent(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(mode="off", capture=False))
    assert recall.prompt("우리 프로젝트는 파이썬 3.10 stdlib만 쓴다") == ""


def test_capture_on_coexists_with_llm_guidance(monkeypatch):
    monkeypatch.setattr(recall, "_cfg",
                        lambda: _cfg(mode="advisory", strategy="llm", capture=True))
    monkeypatch.setattr(recall, "_hits",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no search on llm path")))
    out = recall.prompt("ARIMA와 Prophet 차이 설명해줘")
    assert recall.render_llm_guidance("route") in out
    assert recall.render_capture_cue() in out


def test_capture_off_mode_off_does_not_read_stdin(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(mode="off", capture=False))

    class _Boom:
        def isatty(self):
            return False

        def read(self):
            raise AssertionError("stdin must not be read on the mode=off + capture=off fast path")

    monkeypatch.setattr(recall.sys, "stdin", _Boom())
    assert recall.prompt(None) == ""


def test_capture_on_no_active_vault_suppresses_cue(monkeypatch):
    # Default-on capture must NOT nudge to ingest when there is no wiki to capture into.
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(capture=True))
    monkeypatch.setattr(recall, "_hits", lambda *a, **k: [])          # recall body empty
    monkeypatch.setattr(recall, "_has_active_vault", lambda: False)   # no vault yet
    assert recall.prompt("우리 팀은 파이썬 3.10 stdlib만 쓴다") == ""


def test_capture_on_prepends_strong_hits(monkeypatch):
    monkeypatch.setattr(recall, "_cfg", lambda: _cfg(capture=True))
    monkeypatch.setattr(recall, "_hits",
                        lambda *a, **k: [{"relpath": "wiki/x.md", "title": "X", "score": 9.0, "tags": []}])
    monkeypatch.setattr(recall, "_record_use", lambda *a, **k: None)
    out = recall.prompt("X 페이지에 대해 알려줘")
    assert recall.MARKER in out                    # concrete recall hits present
    assert recall.render_capture_cue() in out      # cue appended after
    assert out.index(recall.MARKER) < out.index(recall.CAPTURE_MARKER)
