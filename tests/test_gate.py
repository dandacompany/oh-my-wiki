from datetime import datetime, timedelta
import pytest
from scripts import gate


def _now():
    return datetime(2026, 6, 23, 10, 0, 0)


def test_note_appends_and_persists_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    gate.note("synthesis", now=_now())
    st = gate.load_state()
    assert [m["kind"] for m in st["markers"]] == ["synthesis"]
    assert st["markers"][0]["at"] == "2026-06-23T10:00:00"


def test_note_rejects_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    with pytest.raises(ValueError):
        gate.note("banana", now=_now())


def test_fresh_markers_prunes_aged(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    gate.note("research", now=_now() - timedelta(minutes=200))  # stale
    gate.note("synthesis", now=_now())                          # fresh
    fresh = gate.fresh_markers(gate.load_state(), now=_now(), ttl_min=120)
    assert [m["kind"] for m in fresh] == ["synthesis"]


def test_load_state_on_corrupt_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    (tmp_path / "gate-state.json").write_text("{not json", encoding="utf-8")
    st = gate.load_state()
    assert st == {"markers": [], "last_prompt_at": None, "snooze_until": None}
