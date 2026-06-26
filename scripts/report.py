"""scripts/report.py — deterministic, read-only vault status + health report.

Aggregates existing signals (registry, layer counts, link graph, lint, review,
doctor, nextstep) into one structured dict. `build()` is best-effort and never
raises; `render()` (see same module) formats the human-readable dashboard.
Creates no data and mutates nothing (beyond an opt-out-able incremental reindex).
"""
from __future__ import annotations

# --- deterministic grading constants (no magic numbers at call sites) ---
_GRADE_THRESHOLD = 20          # total issues above this → NEEDS WORK
_SCORE_PER_ISSUE = 3
_SCORE_PER_PARSE_ERROR = 10
_TOP_TAGS = 5


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _grade(stale, expired, dangling, orphans, lint_issues, parse_errors) -> dict:
    issues = stale + expired + dangling + orphans + lint_issues
    score = max(0, 100 - issues * _SCORE_PER_ISSUE - parse_errors * _SCORE_PER_PARSE_ERROR)
    if parse_errors > 0 or issues > _GRADE_THRESHOLD:
        grade = "NEEDS WORK"
    elif issues == 0:
        grade = "GOOD"
    else:
        grade = "FAIR"
    return {"grade": grade, "score": score, "stale": stale, "expired": expired,
            "dangling": dangling, "orphans": orphans, "lint_issues": lint_issues}


def _wiki_breakdown(db_path, vault_id) -> dict:
    from scripts import registry
    rows = registry.list_notes(db_path, vault_id=vault_id, layer="wiki")

    def pref(p):
        return sum(1 for r in rows if (r["relpath"] or "").startswith(p))
    ent, con, syn = pref("wiki/entities/"), pref("wiki/concepts/"), pref("wiki/syntheses/")
    return {"entities": ent, "concepts": con, "syntheses": syn,
            "other": max(0, len(rows) - ent - con - syn)}


def _facets(db_path, vault_id) -> dict:
    from scripts import registry
    rows = registry.list_notes(db_path, vault_id=vault_id)
    types: dict = {}
    statuses: dict = {}
    pub = priv = 0
    for r in rows:
        t = r["type"] or "—"
        types[t] = types.get(t, 0) + 1
        s = r["status"] or "—"
        statuses[s] = statuses.get(s, 0) + 1
        if r["visibility"] == "public":
            pub += 1
        else:
            priv += 1
    return {"types": types, "statuses": statuses,
            "visibility": {"public": pub, "private": priv}}


def _graph(db_path, vault_id) -> dict:
    from scripts import registry, community
    rep = _safe(lambda: community.analyze(db_path, vault_id=vault_id),
                {"modularity": 0.0, "communities": [], "bridges": [], "hubs": []})
    conn = registry.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM links WHERE vault_id=?",
                             (vault_id,)).fetchone()["n"]
        dangling = conn.execute(
            "SELECT COUNT(*) AS n FROM links WHERE vault_id=? AND dst_note_id IS NULL",
            (vault_id,)).fetchone()["n"]
        nodes = conn.execute(
            "SELECT COUNT(*) AS n FROM notes WHERE vault_id=? AND layer='wiki'",
            (vault_id,)).fetchone()["n"]
    finally:
        conn.close()
    return {"nodes": nodes, "edges": total - dangling, "wikilinks": total,
            "dangling": dangling, "modularity": round(rep.get("modularity", 0.0), 2),
            "communities": len(rep.get("communities") or []),
            "bridges": len(rep.get("bridges") or []),
            "hubs": len(rep.get("hubs") or [])}


def _tags(db_path, vault_id) -> dict:
    from scripts import registry
    conn = registry.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT t.name AS name, COUNT(*) AS n FROM tags t "
            "JOIN note_tags nt ON nt.tag_id = t.id "
            "JOIN notes n ON n.id = nt.note_id "
            "WHERE n.vault_id = ? GROUP BY t.name ORDER BY n DESC, t.name",
            (vault_id,)).fetchall()
    finally:
        conn.close()
    return {"distinct": len(rows), "top": [[r["name"], r["n"]] for r in rows[:_TOP_TAGS]]}


def _inbox(db_path, vault_id) -> dict:
    from scripts import registry
    conn = registry.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM inbox_queue WHERE vault_id=? GROUP BY status",
            (vault_id,)).fetchall()
    finally:
        conn.close()
    out = {"queued": 0, "fetched": 0, "ingested": 0, "failed": 0}
    for r in rows:
        if r["status"] in out:
            out[r["status"]] = r["n"]
    return out


def _index(db_path, vault_id) -> dict:
    from scripts import registry, links
    root = registry.get_vault_root(db_path, vault_id)
    present = (root / "wiki" / "index.md").exists()
    drift = _safe(
        lambda: len(links.index_drift(db_path, vault_id).get("missing_from_index") or []), 0)
    return {"present": present, "drift": drift}


def _parse_errors(db_path, vault_id) -> int:
    from scripts import registry
    conn = registry.connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM notes WHERE vault_id=? AND parse_error=1",
            (vault_id,)).fetchone()["n"]
    finally:
        conn.close()


def _vault_row(db_path, vault_id):
    from scripts import registry
    conn = registry.connect(db_path)
    try:
        return conn.execute("SELECT * FROM vaults WHERE id=?", (vault_id,)).fetchone()
    finally:
        conn.close()


def _active_section(db_path, vault_id, *, today) -> dict:
    from scripts import registry, review, maint
    row = _vault_row(db_path, vault_id)
    layers = _safe(lambda: registry.note_layer_counts(db_path, vault_id), {})
    m = _safe(lambda: maint.status(db_path, vault_id=vault_id, today=today),
              {"stale": 0, "expired": 0})
    due = _safe(lambda: len(review.due_pages(db_path, vault_id=vault_id, today=today)), 0)
    return {
        "name": row["name"] if row else None,
        "path": row["path"] if row else None,
        "mode": row["mode"] if row else None,
        "type": row["type"] if row else None,
        "created_at": row["created_at"] if row else None,
        "last_used": row["last_used"] if row else None,
        "layers": layers,
        "wiki": _safe(lambda: _wiki_breakdown(db_path, vault_id),
                      {"entities": 0, "concepts": 0, "syntheses": 0, "other": 0}),
        "facets": _safe(lambda: _facets(db_path, vault_id),
                        {"types": {}, "statuses": {}, "visibility": {"public": 0, "private": 0}}),
        "graph": _safe(lambda: _graph(db_path, vault_id),
                       {"nodes": 0, "edges": 0, "wikilinks": 0, "dangling": 0,
                        "modularity": 0.0, "communities": 0, "bridges": 0, "hubs": 0}),
        "tags": _safe(lambda: _tags(db_path, vault_id), {"distinct": 0, "top": []}),
        "index": _safe(lambda: _index(db_path, vault_id), {"present": False, "drift": 0}),
        "inbox": _safe(lambda: _inbox(db_path, vault_id),
                       {"queued": 0, "fetched": 0, "ingested": 0, "failed": 0}),
        "review": {"due": due, "stale": m.get("stale", 0), "expired": m.get("expired", 0)},
        "parse_errors": _safe(lambda: _parse_errors(db_path, vault_id), 0),
    }


def _vault_health(db_path, vault_id, *, today) -> dict:
    from scripts import maint, wiki_lint
    m = _safe(lambda: maint.status(db_path, vault_id=vault_id, today=today),
              {"stale": 0, "expired": 0, "lint_issues": 0})
    lint = _safe(lambda: wiki_lint.check(db_path, vault_id=vault_id), {})
    dangling = len(lint.get("dangling_links") or [])
    orphans = len(lint.get("orphan_pages") or [])
    # maint.lint_issues already includes dangling+orphans; subtract to avoid
    # double-counting, so the grade's issue sum == stale+expired+total-lint.
    other_lint = max(0, m.get("lint_issues", 0) - dangling - orphans)
    return _grade(m.get("stale", 0), m.get("expired", 0), dangling, orphans,
                  other_lint, _safe(lambda: _parse_errors(db_path, vault_id), 0))


def _install_health() -> dict:
    from scripts import setup_wizard
    d = setup_wizard.doctor_checks()
    return {"ok": d.get("ok", False),
            "items": [{"name": i["name"], "ok": i["ok"], "hint": i.get("hint", "")}
                      for i in d.get("items", [])]}


def _next_top(db_path, vault_id, *, today, n=3) -> list:
    from scripts import nextstep
    sig = nextstep.signals(db_path, vault_id, today=today)
    return nextstep.suggest(sig)[:n]


def build(db_path, vault_id=None, *, today, no_reindex=False) -> dict:
    """Aggregate the full report dict. Best-effort; never raises."""
    from scripts import registry, banner
    out = {
        "generated_at": today,
        "omw_version": _safe(banner.version, "?"),
        "vaults": {"active": None, "total": 0, "list": []},
        "active_vault": None,
        "health": {"install": _safe(_install_health, None), "vault": None},
        "next": [],
    }
    vaults = _safe(lambda: registry.list_vaults(db_path), [])
    active = _safe(lambda: registry.get_active(db_path), None)
    out["vaults"]["active"] = active["name"] if active else None
    out["vaults"]["total"] = len(vaults)
    vlist = []
    for v in vaults:
        entry = _safe(lambda v=v: {
            "name": v["name"], "mode": v["mode"], "type": v["type"],
            "total_notes": _safe(lambda v=v: sum(registry.note_layer_counts(db_path, v["id"]).values()), 0),
            "is_active": bool(v["is_active"]),
            "archived": v["archived_at"] is not None,
        }, None)
        if entry is not None:
            vlist.append(entry)
    out["vaults"]["list"] = vlist

    target_id = vault_id if vault_id is not None else (active["id"] if active else None)
    if target_id is None:
        return out

    if not no_reindex:
        def _ri():
            from scripts import reindex
            reindex.incremental(db_path, vault_id=target_id)
        _safe(_ri, None)

    out["active_vault"] = _safe(lambda: _active_section(db_path, target_id, today=today), None)
    out["health"]["vault"] = _safe(lambda: _vault_health(db_path, target_id, today=today), None)
    out["next"] = _safe(lambda: _next_top(db_path, target_id, today=today), [])
    return out
