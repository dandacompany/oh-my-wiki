"""omw maintenance gate — host-agnostic engine for the upkeep/capture prompt.

Sibling of scripts/recall.py: recall reads knowledge IN, the gate prompts to push
knowledge OUT and keep it fresh. Best-effort and non-blocking — the host hook's
stdout is injected as agent context; empty output means "no injection". Never
raises to the host. The engine takes an injected `now` for deterministic tests.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.paths import omw_home

MARKER = "omw-gate"
MARKER_KINDS = ("research", "synthesis", "ingest", "recall-stale")
_DEFAULT_STATE = {"markers": [], "last_prompt_at": None, "snooze_until": None}


def state_path() -> Path:
    return omw_home() / "gate-state.json"


def load_state() -> dict:
    p = state_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        return dict(_DEFAULT_STATE, markers=[])
    for k, v in _DEFAULT_STATE.items():
        data.setdefault(k, v)
    if not isinstance(data.get("markers"), list):
        data["markers"] = []
    return data


def save_state(state: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def fresh_markers(state: dict, *, now: datetime, ttl_min: int = 120) -> list[dict]:
    out = []
    for m in state.get("markers", []):
        try:
            age = (now - _parse(m["at"])).total_seconds() / 60.0
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= age <= ttl_min:
            out.append(m)
    return out


def note(kind: str, *, now: datetime, ttl_min: int = 120) -> dict:
    if kind not in MARKER_KINDS:
        raise ValueError(f"unknown marker kind {kind!r}; expected one of {MARKER_KINDS}")
    state = load_state()
    state["markers"] = fresh_markers(state, now=now, ttl_min=ttl_min)
    state["markers"].append({"kind": kind, "at": now.isoformat()})
    save_state(state)
    return state


DEFAULT_THRESHOLD = {"stale": 1, "lint": 3}


def debt_pending(maint_status: dict, *, threshold: dict) -> list[str]:
    stale = (maint_status.get("stale", 0) or 0) + (maint_status.get("expired", 0) or 0)
    lint = maint_status.get("lint_issues", 0) or 0
    if stale >= threshold.get("stale", 1) or lint >= threshold.get("lint", 3):
        return ["upkeep"]
    return []


def marker_pending(markers: list[dict]) -> list[str]:
    kinds = {m.get("kind") for m in markers}
    out = []
    if kinds & {"research", "synthesis", "ingest"}:
        out += ["capture", "reindex"]
    if "recall-stale" in kinds:
        out += ["recall"]
    return out
