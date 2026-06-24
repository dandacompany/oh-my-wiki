"""Deterministic next-step recommender — reads vault lifecycle signals and ranks
the most fitting next action (collect/structure/synthesize/maintain/review/recall).
Read-only; never writes; never raises. Sibling of gate.py (gate = passive turn-end
maintenance backstop; nextstep = active on-demand lifecycle recommender). The skill
runs `omw next` after a unit of work and proposes the top suggestion."""
from __future__ import annotations

from datetime import datetime


def _count(db_path, vault_id, layer, prefix):
    from scripts import registry
    try:
        rows = registry.list_notes(db_path, vault_id=vault_id, layer=layer)
        return sum(1 for r in rows if (r["relpath"] or "").startswith(prefix))
    except Exception:
        return 0


def signals(db_path, vault_id, *, today: str, now=None) -> dict:
    from scripts import maint, gate, community
    raw = _count(db_path, vault_id, "raw", "raw/")
    entities = _count(db_path, vault_id, "wiki", "wiki/entities/")
    concepts = _count(db_path, vault_id, "wiki", "wiki/concepts/")
    syntheses = _count(db_path, vault_id, "wiki", "wiki/syntheses/")
    stale = expired = lint_issues = 0
    try:
        m = maint.status(db_path, vault_id=vault_id, today=today)
        stale, expired, lint_issues = m.get("stale", 0), m.get("expired", 0), m.get("lint_issues", 0)
    except Exception:
        pass
    markers: list[str] = []
    try:
        _now = now or datetime.fromisoformat(today)
        markers = [m.get("kind") for m in gate.fresh_markers(gate.load_state(), now=_now)]
    except Exception:
        pass
    clusters = 0
    try:
        clusters = len(community.analyze(db_path, vault_id=vault_id).get("communities") or [])
    except Exception:
        pass
    return {"raw": raw, "entities": entities, "concepts": concepts,
            "syntheses": syntheses, "lint_issues": lint_issues, "stale": stale,
            "expired": expired, "markers": markers, "clusters": clusters}


def suggest(sig: dict) -> list[dict]:
    out: list[dict] = []
    structured = sig["entities"] + sig["concepts"]
    if sig["lint_issues"] > 0:
        out.append({"action": "maintain", "command": "omw lint   (then fix / omw supersede)",
                    "reason": f"{sig['lint_issues']} lint issue(s)", "phase": "maintain"})
    if sig["stale"] + sig["expired"] > 0:
        out.append({"action": "review", "command": "omw review audit",
                    "reason": f"{sig['stale'] + sig['expired']} page(s) stale/expired", "phase": "review"})
    if sig["raw"] > 0 and structured == 0:
        out.append({"action": "structure", "command": "(omw skill) ingest raw → entities/concepts",
                    "reason": "raw collected, none structured yet", "phase": "structure"})
    if structured > 0 and sig["syntheses"] == 0 and sig["clusters"] > 0:
        out.append({"action": "synthesize",
                    "command": "omw connections   →   (omw skill) synthesis draft",
                    "reason": f"{structured} structured page(s), {sig['clusters']} cluster(s), no synthesis",
                    "phase": "synthesize"})
    if "research" in sig.get("markers", []):
        out.append({"action": "collect", "command": "omw search \"<query>\"   →   omw fetch",
                    "reason": "active research thread", "phase": "collect"})
    out.append({"action": "recall", "command": "omw find \"<topic>\"",
                "reason": "check existing knowledge before new work", "phase": "recall"})
    return out
