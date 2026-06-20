# scripts/maint.py
"""Deterministic knowledge-maintenance status — a session-start nudge and a
cron-friendly health summary. Rolls up review.audit (freshness) + wiki_lint.check
(structural signals) into counts. Best-effort: never raises (callers run in hooks)."""
from __future__ import annotations

from pathlib import Path

from scripts import review, wiki_lint

#: lint report keys that count as a fixable issue (each list element = 1 issue).
_LINT_KEYS = ("dangling_links", "orphans", "contradiction_candidates",
              "stale_claim_candidates", "missing_concepts")


def status(db_path, *, vault_id: int, today: str) -> dict:
    """Return {stale, expired, lint_issues, nudge}. `nudge` is a one-line agent
    hint, empty when nothing is due. All sub-calls are guarded (hook hot path)."""
    stale = expired = 0
    try:
        for row in review.audit(db_path, vault_id=vault_id, today=today, apply=False) or []:
            st = row.get("state")
            if st == "stale":
                stale += 1
            elif st == "expired":
                expired += 1
    except Exception:
        pass

    lint_issues = 0
    try:
        rep = wiki_lint.check(db_path, vault_id=vault_id) or {}
        for k in _LINT_KEYS:
            lint_issues += len(rep.get(k) or [])
    except Exception:
        pass

    nudge = ""
    if stale or expired or lint_issues:
        bits = []
        if stale:
            bits.append(f"{stale} stale")
        if expired:
            bits.append(f"{expired} expired")
        if lint_issues:
            bits.append(f"{lint_issues} lint issue(s)")
        nudge = ("지식 유지보수 권장: " + ", ".join(bits)
                 + " — `/omw lint` 또는 `omw review audit`로 점검하세요.")
    return {"stale": stale, "expired": expired, "lint_issues": lint_issues, "nudge": nudge}
