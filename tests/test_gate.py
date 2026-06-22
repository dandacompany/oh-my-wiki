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


def test_debt_pending_respects_threshold():
    below = {"stale": 0, "expired": 0, "lint_issues": 2, "nudge": ""}
    assert gate.debt_pending(below, threshold={"stale": 1, "lint": 3}) == []
    above_lint = {"stale": 0, "expired": 0, "lint_issues": 3, "nudge": ""}
    assert gate.debt_pending(above_lint, threshold={"stale": 1, "lint": 3}) == ["upkeep"]
    above_stale = {"stale": 1, "expired": 0, "lint_issues": 0, "nudge": ""}
    assert gate.debt_pending(above_stale, threshold={"stale": 1, "lint": 3}) == ["upkeep"]


def test_marker_pending_maps_kinds_stably():
    markers = [{"kind": "synthesis", "at": "x"}, {"kind": "ingest", "at": "y"},
               {"kind": "recall-stale", "at": "z"}]
    assert gate.marker_pending(markers) == ["capture", "reindex", "recall"]
    assert gate.marker_pending([]) == []


ORDER = ["capture", "reindex", "recall", "upkeep"]
CLEAN = {"stale": 0, "expired": 0, "lint_issues": 0, "nudge": ""}
DEBT = {"stale": 2, "expired": 0, "lint_issues": 0, "nudge": ""}


def _cfg(**kw):
    base = {"cooldown_min": 30, "marker_ttl_min": 120, "threshold": {"stale": 1, "lint": 3}}
    base.update(kw)
    return base


def test_decide_closed_when_nothing_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    d = gate.decide(gate.load_state(), CLEAN, now=_now(), cfg=_cfg())
    assert d["open"] is False and d["pending"] == []


def test_decide_open_on_fresh_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    gate.note("synthesis", now=_now())
    d = gate.decide(gate.load_state(), CLEAN, now=_now(), cfg=_cfg())
    assert d["open"] is True
    assert d["pending"] == ["capture", "reindex"]
    assert [p for p in d["pending"] if p in ORDER] == d["pending"]  # stable order


def test_decide_open_on_debt_only(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    d = gate.decide(gate.load_state(), DEBT, now=_now(), cfg=_cfg())
    assert d["open"] is True and d["pending"] == ["upkeep"]


def test_decide_blocked_by_cooldown(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    gate.note("synthesis", now=_now())
    st = gate.record_prompt(gate.load_state(), now=_now())
    d = gate.decide(st, CLEAN, now=_now() + timedelta(minutes=10), cfg=_cfg(cooldown_min=30))
    assert d["open"] is False and d["reason"] == "cooldown"


def test_defer_snoozes_and_clears(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "omw_home", lambda: tmp_path)
    gate.note("synthesis", now=_now())
    st = gate.defer(gate.load_state(), now=_now(), cooldown_min=30)
    assert st["markers"] == []
    d = gate.decide(st, DEBT, now=_now() + timedelta(minutes=5), cfg=_cfg())
    assert d["open"] is False and d["reason"] == "snoozed"
