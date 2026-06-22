"""omw maintenance gate — host-agnostic engine for the upkeep/capture prompt.

Sibling of scripts/recall.py: recall reads knowledge IN, the gate prompts to push
knowledge OUT and keep it fresh. Best-effort and non-blocking — the host hook's
stdout is injected as agent context; empty output means "no injection". Never
raises to the host. The engine takes an injected `now` for deterministic tests.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
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


_PENDING_ORDER = ["capture", "reindex", "recall", "upkeep"]


def _minutes_since(ts, now):
    if not ts:
        return None
    try:
        return (now - _parse(ts)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None


def decide(state, maint_status, *, now, cfg) -> dict:
    ttl = cfg.get("marker_ttl_min", 120)
    threshold = cfg.get("threshold", DEFAULT_THRESHOLD)
    fresh = fresh_markers(state, now=now, ttl_min=ttl)
    pending = marker_pending(fresh) + debt_pending(maint_status, threshold=threshold)
    pending = [p for p in _PENDING_ORDER if p in set(pending)]
    if not pending:
        return {"open": False, "pending": [], "reason": "nothing-pending"}
    snooze = state.get("snooze_until")
    if snooze:
        rem = _minutes_since(snooze, now)
        if rem is not None and rem < 0:
            return {"open": False, "pending": pending, "reason": "snoozed"}
    since = _minutes_since(state.get("last_prompt_at"), now)
    if since is not None and since < cfg.get("cooldown_min", 30):
        return {"open": False, "pending": pending, "reason": "cooldown"}
    return {"open": True, "pending": pending, "reason": "open"}


def record_prompt(state, *, now) -> dict:
    state["last_prompt_at"] = now.isoformat()
    save_state(state)
    return state


def defer(state, *, now, cooldown_min) -> dict:
    state["snooze_until"] = (now + timedelta(minutes=cooldown_min)).isoformat()
    state["markers"] = []
    save_state(state)
    return state


def accept(state, *, now) -> dict:
    state["markers"] = []
    state["last_prompt_at"] = now.isoformat()
    save_state(state)
    return state


PART_LABEL = {
    "capture": "capture this session's research/synthesis into the wiki",
    "reindex": "reindex + refresh connections",
    "recall": "review recalled pages for staleness",
    "upkeep": "clear lint / refresh stale pages",
}


def render(decision: dict, *, mode: str) -> str:
    if mode == "off" or not decision.get("open"):
        return ""
    items = "\n".join(f"  - {PART_LABEL.get(p, p)}" for p in decision["pending"])
    if mode == "enforce":
        body = (
            "Pending wiki upkeep detected:\n" + items + "\n"
            "Before ending this turn, ask the user whether to run it now (foreground), "
            "in the background (omw team-run), or later. Apply nothing without confirmation."
        )
    else:  # advisory
        body = (
            "Pending wiki upkeep:\n" + items + "\n"
            "If it fits the moment, offer to run the upkeep cycle (foreground or background)."
        )
    return f"<{MARKER}>\n{body}\n</{MARKER}>"


import shutil


def _omw_bin() -> str:
    return shutil.which("omw") or "omw"


def _gate_hook_specs() -> dict:
    omw = _omw_bin()
    return {"Stop": (f'"{omw}" gate check', "omw wiki upkeep gate")}


def _event_has_gate(entries: list) -> bool:
    for group in entries or []:
        for h in (group or {}).get("hooks", []):
            if "gate check" in (h or {}).get("command", ""):
                return True
    return False


def _host_path(host, config_path):
    from scripts import recall
    return Path(config_path) if config_path else recall.host_hook_configs().get(host)


def _load_host(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as e:
        return None, f"unreadable {path}: {e}"
    if not isinstance(data, dict):
        return None, f"unexpected config shape in {path}"
    return data, None


def _backup_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_suffix(path.suffix + ".omw-bak")
        if not bak.exists():
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wire_host(host, *, config_path=None) -> tuple[bool, str]:
    path = _host_path(host, config_path)
    if path is None:
        return False, f"unknown host {host!r}"
    data, err = _load_host(path)
    if err:
        return False, err
    hooks = data.setdefault("hooks", {})
    added = []
    for event, (command, status) in _gate_hook_specs().items():
        entries = hooks.setdefault(event, [])
        if _event_has_gate(entries):
            continue
        entries.append({"hooks": [{"type": "command", "command": command,
                                   "timeout": 5, "statusMessage": status}]})
        added.append(event)
    if not added:
        return False, f"already wired ({path})"
    try:
        _backup_write(path, data)
    except OSError as e:
        return False, f"write failed {path}: {e}"
    return True, f"wired {'+'.join(added)} → {path}"


def unwire_host(host, *, config_path=None) -> tuple[bool, str]:
    path = _host_path(host, config_path)
    if path is None or not path.exists():
        return False, "nothing to unwire"
    data, err = _load_host(path)
    if err:
        return False, err
    hooks = data.get("hooks", {})
    changed = False
    for event in list(hooks):
        kept = [g for g in hooks[event]
                if not any("gate check" in (h or {}).get("command", "")
                           for h in (g or {}).get("hooks", []))]
        if len(kept) != len(hooks[event]):
            hooks[event] = kept
            changed = True
    if not changed:
        return False, "nothing to unwire"
    try:
        _backup_write(path, data)
    except OSError as e:
        return False, f"write failed {path}: {e}"
    return True, f"unwired → {path}"
