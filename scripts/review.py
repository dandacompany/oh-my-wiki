"""Spaced-repetition review schedule for wiki pages (frontmatter `review:` block).

Pure scheduling math + two vault-I/O helpers. `today` is injected (YYYY-MM-DD)
so tests are deterministic; the CLI defaults it to date.today().
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from scripts import frontmatter, links, reindex

_TIERS = {"high": 90, "medium": 30, "low": 7}
_EXEMPT = set(links.META_RELPATHS)
_MAX_INTERVAL = 365
_TIER_ORDER = ("high", "medium", "low")


def tier(confidence) -> int:
    return _TIERS.get(confidence, 30)


# --- Deterministic freshness layer (Hermes-style time/state, no numeric score) ---

def overdue_ratio(due, today: str, interval_days) -> float | None:
    """How far past `due` the page is, normalized by its interval.
    0 = exactly due, 1 = one full interval overdue, ≥2 = expired. None if unscheduled."""
    if not due or not interval_days:
        return None
    try:
        ivl = int(interval_days)
        if ivl <= 0:
            return None
        gap = (date.fromisoformat(today) - date.fromisoformat(str(due))).days
    except (ValueError, TypeError):
        return None
    return gap / ivl


def staleness_state(ratio: float | None) -> str:
    """fresh (< due) · due (0–1) · stale (1–2 intervals overdue) · expired (≥2) · unscheduled."""
    if ratio is None:
        return "unscheduled"
    if ratio < 0:
        return "fresh"
    if ratio < 1:
        return "due"
    if ratio < 2:
        return "stale"
    return "expired"


def demote(confidence) -> str:
    """One tier down (high→medium→low); unknown/None → low. Deterministic, never promotes."""
    if confidence in _TIER_ORDER:
        return _TIER_ORDER[min(_TIER_ORDER.index(confidence) + 1, len(_TIER_ORDER) - 1)]
    return "low"


def _used_recently(last_used_iso, today: str, interval_days) -> bool:
    """True if the page was surfaced within its own interval window (reactivation)."""
    if not last_used_iso or not interval_days:
        return False
    try:
        gap = (date.fromisoformat(today) - date.fromisoformat(str(last_used_iso))).days
        return 0 <= gap < int(interval_days)
    except (ValueError, TypeError):
        return False


def record_use(db_path: Path, *, vault_id: int, relpaths, today: str) -> bool:
    """Stamp pages as used today in the vault usage side store (reactivates freshness)."""
    from scripts import usage
    return usage.bump(reindex._vault_path(db_path, vault_id), relpaths, today)


def audit(db_path: Path, *, vault_id: int, today: str, apply: bool = False) -> list[dict]:
    """Deterministic freshness audit (report-only unless apply=True).

    - `expired` (≥2 intervals overdue, not used recently) → propose confidence demotion + needs_reconfirm
    - `stale`   (≥1 interval overdue)                     → propose stale flag
    - `pin: true` pages are exempt; real recent use (usage store) reactivates → no action.
    Promotion is never automatic — restoring confidence stays with the agent + user
    (propose → confirm → execute). With apply=True, only writes flags/demotions, then reindexes.
    """
    from scripts import usage
    root = reindex._vault_path(db_path, vault_id)
    used = usage.last_used(root)
    out: list[dict] = []
    changed = False
    for md in sorted(root.rglob("*.md")):
        if ".trash" in md.parts:
            continue
        rel = str(md.relative_to(root)).replace("\\", "/")
        if rel in _EXEMPT or rel.startswith("raw/"):
            continue
        try:
            meta, body = frontmatter.parse(md.read_text(encoding="utf-8"))
        except frontmatter.FrontmatterError:
            continue
        if meta.get("pin") is True or meta.get("pinned") is True:
            continue
        rv = meta.get("review") if isinstance(meta.get("review"), dict) else {}
        conf = meta.get("confidence")
        interval = rv.get("interval_days") or tier(conf)
        ratio = overdue_ratio(rv.get("due"), today, interval)
        state = staleness_state(ratio)
        if _used_recently(used.get(rel), today, interval):
            state = "fresh"  # reactivated by real use
        if state not in ("stale", "expired"):
            continue
        new_conf = demote(conf) if state == "expired" else conf
        action = "demote+reconfirm" if new_conf != conf else (
            "reconfirm" if state == "expired" else "flag-stale")
        out.append({
            "relpath": rel, "state": state,
            "overdue_ratio": round(ratio, 2) if ratio is not None else None,
            "confidence": conf, "proposed_confidence": new_conf, "action": action,
        })
        if apply:
            if new_conf != conf:
                meta["confidence"] = new_conf
            if state == "expired":
                meta["needs_reconfirm"] = True
            meta["stale"] = True
            md.write_text(frontmatter.dump(meta, body), encoding="utf-8")
            changed = True
    if apply and changed:
        reindex.incremental(db_path, vault_id=vault_id)
    out.sort(key=lambda r: (r["action"], r["relpath"]))
    return out


def next_interval(prev_interval_days, grade: str, confidence) -> int:
    base = tier(confidence)
    if grade == "needs-work":
        return base
    if grade == "pass":
        if not prev_interval_days:
            return base
        return min(prev_interval_days * 2, _MAX_INTERVAL)
    raise ValueError(f"unknown grade: {grade!r}")


def schedule_fields(today: str, interval_days: int) -> dict:
    due = date.fromisoformat(today) + timedelta(days=interval_days)
    return {"last": today, "due": due.isoformat(), "interval_days": interval_days}


def due_pages(db_path: Path, *, vault_id: int, today: str,
              include_unscheduled: bool = True) -> list[dict]:
    """Pages due for review on `today`. Unscheduled (no review block) → due."""
    root = reindex._vault_path(db_path, vault_id)
    out: list[dict] = []
    for md in sorted(root.rglob("*.md")):
        if ".trash" in md.parts:
            continue
        rel = str(md.relative_to(root)).replace("\\", "/")
        if rel in _EXEMPT or rel.startswith("raw/"):
            continue
        try:
            meta, _ = frontmatter.parse(md.read_text(encoding="utf-8"))
        except frontmatter.FrontmatterError:
            continue
        rv = meta.get("review") if isinstance(meta.get("review"), dict) else {}
        due = rv.get("due")
        confidence = meta.get("confidence")
        if due is not None:
            if str(due) <= today:  # zero-padded ISO dates compare lexicographically
                out.append({"relpath": rel, "due": str(due),
                            "interval_days": rv.get("interval_days"), "confidence": confidence})
        elif include_unscheduled:
            out.append({"relpath": rel, "due": None, "interval_days": None,
                        "confidence": confidence})
    out.sort(key=lambda r: (r["due"] is not None, r["due"] or ""))
    return out


def reschedule(db_path: Path, *, vault_id: int, relpath: str, grade: str,
               today: str) -> dict:
    """Re-verify outcome → recompute the schedule, write frontmatter, reindex."""
    root = reindex._vault_path(db_path, vault_id)
    abs_path = root / relpath
    if not abs_path.exists():
        raise FileNotFoundError(f"page not found: {relpath}")
    meta, body = frontmatter.parse(abs_path.read_text(encoding="utf-8"))
    rv = meta.get("review") if isinstance(meta.get("review"), dict) else {}
    interval = next_interval(rv.get("interval_days"), grade, meta.get("confidence"))
    meta["review"] = schedule_fields(today, interval)
    abs_path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    reindex.incremental(db_path, vault_id=vault_id)
    return {"relpath": relpath, "review": meta["review"]}
