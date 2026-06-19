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
