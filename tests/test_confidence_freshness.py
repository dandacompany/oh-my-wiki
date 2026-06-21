"""Deterministic confidence-freshness layer (B: stale/demote + C: use-reactivation)."""
import os

from scripts import frontmatter, registry, review, usage
from scripts.paths import registry_path

TODAY = "2026-06-19"


# --- pure functions -----------------------------------------------------------------

def test_overdue_ratio_and_state():
    assert review.overdue_ratio(None, TODAY, 30) is None          # unscheduled
    assert review.overdue_ratio("2026-06-19", TODAY, 30) == 0.0    # exactly due
    assert review.overdue_ratio("2026-05-20", TODAY, 30) == 1.0    # 30d overdue / 30 = 1.0
    assert review.staleness_state(None) == "unscheduled"
    assert review.staleness_state(-0.5) == "fresh"
    assert review.staleness_state(0.5) == "due"
    assert review.staleness_state(1.5) == "stale"
    assert review.staleness_state(2.5) == "expired"


def test_demote_never_promotes():
    assert review.demote("high") == "medium"
    assert review.demote("medium") == "low"
    assert review.demote("low") == "low"      # floors at low
    assert review.demote(None) == "low"


def test_used_recently():
    assert review._used_recently("2026-06-18", TODAY, 30) is True
    assert review._used_recently("2026-01-01", TODAY, 30) is False
    assert review._used_recently(None, TODAY, 30) is False


# --- usage side store ---------------------------------------------------------------

def test_usage_bump_roundtrip(tmp_path):
    assert usage.last_used(tmp_path) == {}
    assert usage.bump(tmp_path, ["wiki/a.md", "wiki/b.md"], TODAY) is True
    assert usage.last_used(tmp_path) == {"wiki/a.md": TODAY, "wiki/b.md": TODAY}
    assert usage.bump(tmp_path, [], TODAY) is False  # nothing to record


# --- audit integration --------------------------------------------------------------

def _page(conf, due, *, pin=False):
    meta = {"title": "P", "type": "concept", "confidence": conf,
            "review": {"due": due, "interval_days": review.tier(conf)}}
    if pin:
        meta["pin"] = True
    return frontmatter.dump(meta, "# body\n")


def _vault(tmp_path):
    os.environ["OMW_HOME"] = str(tmp_path / "home")
    db = registry_path()
    registry.init_db(db)
    root = tmp_path / "v"
    (root / "wiki" / "concepts").mkdir(parents=True)
    v = registry.add_vault(db, name="t", path=root, type_="markdown", mode="wiki")
    return db, v["id"], root


def test_audit_reports_and_applies(tmp_path):
    db, vid, root = _vault(tmp_path)
    cc = root / "wiki" / "concepts"
    (cc / "expired.md").write_text(_page("high", "2025-12-01"), encoding="utf-8")   # ~200d/90 ≈ 2.2 → expired
    (cc / "stale.md").write_text(_page("medium", "2026-05-10"), encoding="utf-8")   # 40d/30 ≈ 1.3 → stale
    (cc / "fresh.md").write_text(_page("high", "2026-12-01"), encoding="utf-8")     # future → fresh
    (cc / "pinned.md").write_text(_page("high", "2025-01-01", pin=True), encoding="utf-8")  # exempt
    try:
        # report-only
        rep = review.audit(db, vault_id=vid, today=TODAY, apply=False)
        by = {r["relpath"]: r for r in rep}
        assert "wiki/concepts/expired.md" in by and by["wiki/concepts/expired.md"]["action"] == "demote+reconfirm"
        assert by["wiki/concepts/expired.md"]["proposed_confidence"] == "medium"
        assert by["wiki/concepts/stale.md"]["action"] == "flag-stale"
        assert "wiki/concepts/fresh.md" not in by      # fresh → no finding
        assert "wiki/concepts/pinned.md" not in by     # pinned → exempt
        # report-only must NOT mutate
        m, _ = frontmatter.parse((cc / "expired.md").read_text(encoding="utf-8"))
        assert m["confidence"] == "high" and "stale" not in m

        # apply
        review.audit(db, vault_id=vid, today=TODAY, apply=True)
        m2, _ = frontmatter.parse((cc / "expired.md").read_text(encoding="utf-8"))
        assert m2["confidence"] == "medium" and m2["stale"] is True and m2["needs_reconfirm"] is True
        ms, _ = frontmatter.parse((cc / "stale.md").read_text(encoding="utf-8"))
        assert ms["stale"] is True and ms["confidence"] == "medium"   # stale flagged, not demoted
    finally:
        os.environ.pop("OMW_HOME", None)


def test_audit_lint_signal_flags_fresh_page(tmp_path):
    # A time-FRESH page (due in the future) that has a broken outbound link
    # must still be flagged stale via the deterministic lint signal.
    db, vid, root = _vault(tmp_path)
    meta = {"title": "P", "type": "concept", "confidence": "high",
            "review": {"due": "2026-12-01", "interval_days": 90}}
    body = "# body\n\nsee [gone](./does-not-exist.md)\n"
    (root / "wiki" / "concepts" / "broken.md").write_text(
        frontmatter.dump(meta, body), encoding="utf-8")
    try:
        rep = review.audit(db, vault_id=vid, today=TODAY, apply=False)
        by = {r["relpath"]: r for r in rep}
        hit = by.get("wiki/concepts/broken.md")
        assert hit is not None and hit["action"] == "flag-stale"
        assert "broken-link" in hit["signals"]
    finally:
        os.environ.pop("OMW_HOME", None)


def test_audit_reactivation_by_use(tmp_path):
    db, vid, root = _vault(tmp_path)
    (root / "wiki" / "concepts" / "expired.md").write_text(_page("high", "2025-12-01"), encoding="utf-8")
    try:
        # mark used today → reactivated → no finding
        review.record_use(db, vault_id=vid, relpaths=["wiki/concepts/expired.md"], today=TODAY)
        rep = review.audit(db, vault_id=vid, today=TODAY, apply=False)
        assert rep == []
    finally:
        os.environ.pop("OMW_HOME", None)


# --- lint-signal surfacing (Task 3) ------------------------------------------------

def test_lint_signal_failure_is_surfaced_not_silent(monkeypatch):
    from scripts import review
    import scripts.wiki_lint as wl
    monkeypatch.setattr(wl, "check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    sig, warn = review._lint_signals(None, vault_id=1)
    assert sig == {} and warn is not None and "lint" in warn.lower()


def test_lint_signals_success_returns_no_warning(monkeypatch):
    from scripts import review
    import scripts.wiki_lint as wl
    monkeypatch.setattr(wl, "check", lambda *a, **k: {"dangling_links": [], "contradiction_candidates": [], "stale_claim_candidates": []})
    sig, warn = review._lint_signals(None, vault_id=1)
    assert warn is None


def test_audit_happy_path_has_no_lint_unavailable_entry(tmp_path):
    """Normal audit (lint healthy) must NOT include a lint_unavailable warning."""
    db, vid, root = _vault(tmp_path)
    (root / "wiki" / "concepts" / "stale.md").write_text(
        _page("medium", "2026-05-10"), encoding="utf-8")
    try:
        rep = review.audit(db, vault_id=vid, today=TODAY, apply=False)
        kinds = [r.get("kind") for r in rep]
        assert "lint_unavailable" not in kinds
    finally:
        os.environ.pop("OMW_HOME", None)


def test_audit_surfaces_lint_warning_on_failure(tmp_path, monkeypatch):
    """When lint raises, audit output includes a lint_unavailable entry."""
    import scripts.wiki_lint as wl
    monkeypatch.setattr(wl, "check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    db, vid, root = _vault(tmp_path)
    (root / "wiki" / "concepts" / "stale.md").write_text(
        _page("medium", "2026-05-10"), encoding="utf-8")
    try:
        rep = review.audit(db, vault_id=vid, today=TODAY, apply=False)
        lint_entries = [r for r in rep if r.get("kind") == "lint_unavailable"]
        assert len(lint_entries) == 1
        assert "lint" in lint_entries[0]["detail"].lower()
        assert lint_entries[0]["relpath"] is None
    finally:
        os.environ.pop("OMW_HOME", None)


def test_lint_signal_importerror_is_surfaced_not_silent(monkeypatch):
    import sys
    from scripts import review

    # `_lint_signals` does `from scripts import wiki_lint` (a local import).
    # To force an ImportError from that statement we install a finder that
    # raises ImportError for the fully-qualified module name.
    import importlib
    import importlib.abc
    import importlib.machinery

    class _FailFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "scripts.wiki_lint":
                raise ImportError("no wiki_lint (injected by test)")
            return None

    finder = _FailFinder()
    # Remove cached copy so the finder is actually consulted
    monkeypatch.delitem(sys.modules, "scripts.wiki_lint", raising=False)
    sys.meta_path.insert(0, finder)
    try:
        sig, warn = review._lint_signals(None, vault_id=1)
    finally:
        sys.meta_path.remove(finder)
    assert sig == {} and warn is not None and "lint" in warn.lower()
