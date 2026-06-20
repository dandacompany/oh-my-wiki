# tests/test_maint.py
from scripts import maint


def test_status_empty_is_silent(monkeypatch):
    monkeypatch.setattr(maint.review, "audit", lambda *a, **k: [])
    monkeypatch.setattr(maint.wiki_lint, "check", lambda *a, **k: {})
    out = maint.status(db_path=None, vault_id=1, today="2026-06-21")
    assert out == {"stale": 0, "expired": 0, "lint_issues": 0, "nudge": ""}


def test_status_counts_and_nudge(monkeypatch):
    monkeypatch.setattr(maint.review, "audit", lambda *a, **k: [
        {"relpath": "wiki/a.md", "state": "stale"},
        {"relpath": "wiki/b.md", "state": "expired"},
    ])
    monkeypatch.setattr(maint.wiki_lint, "check", lambda *a, **k: {
        "dangling_links": [{"source": "wiki/a.md"}],
        "orphans": [{"relpath": "wiki/c.md"}],
    })
    out = maint.status(db_path=None, vault_id=1, today="2026-06-21")
    assert out["stale"] == 1 and out["expired"] == 1 and out["lint_issues"] == 2
    assert "1 stale" in out["nudge"] and "/omw lint" in out["nudge"]
