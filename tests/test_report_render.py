from scripts import report


def _data(**over):
    base = {
        "generated_at": "2026-06-26", "omw_version": "9.9.9",
        "vaults": {"active": "default", "total": 1, "list": [
            {"name": "default", "mode": "wiki", "type": "markdown",
             "total_notes": 3, "is_active": True, "archived": False}]},
        "active_vault": {
            "name": "default", "path": "/v", "mode": "wiki", "type": "markdown",
            "created_at": "x", "last_used": "y",
            "layers": {"raw": 1, "wiki": 2}, "wiki": {"entities": 1, "concepts": 1,
            "syntheses": 0, "other": 0},
            "facets": {"types": {"concept": 1}, "statuses": {"active": 2},
                       "visibility": {"public": 0, "private": 2}},
            "graph": {"nodes": 2, "edges": 1, "wikilinks": 2, "dangling": 1,
                      "modularity": 0.5, "communities": 1, "bridges": 0, "hubs": 0},
            "tags": {"distinct": 2, "top": [["ai", 2], ["llm", 1]]},
            "index": {"present": True, "drift": 0},
            "inbox": {"queued": 0, "fetched": 0, "ingested": 0, "failed": 0},
            "review": {"due": 0, "stale": 0, "expired": 0},
            "parse_errors": 0,
        },
        "health": {"install": {"ok": True, "items": [
            {"name": "yt-dlp", "ok": True, "hint": ""},
            {"name": "chromium", "ok": False, "hint": "x"}]},
            "vault": {"grade": "FAIR", "score": 90, "stale": 0, "expired": 0,
                      "dangling": 1, "orphans": 0, "lint_issues": 0}},
        "next": [{"action": "recall", "command": "omw find \"x\"", "reason": "check"}],
    }
    base.update(over)
    return base


def test_render_has_sections():
    out = report.render(_data())
    for header in ("VAULTS", "ACTIVE VAULT", "HEALTH", "NEXT"):
        assert header in out
    assert "default" in out
    assert "FAIR" in out
    assert "omw 9.9.9" in out


def test_render_omits_zero_inbox():
    out = report.render(_data())
    # inbox all-zero → no "Inbox" row
    assert "Inbox" not in out
    # tags present → tags row shows
    assert "ai" in out


def test_render_no_active_vault():
    out = report.render(_data(active_vault=None, health={"install": None, "vault": None},
                              vaults={"active": None, "total": 0, "list": []}, next=[]))
    assert "no active vault" in out
    assert "ACTIVE VAULT" in out
