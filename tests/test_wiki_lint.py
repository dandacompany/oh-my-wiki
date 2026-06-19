from pathlib import Path
import shutil
import time
import os

import pytest

from scripts import registry, adapters, reindex, wiki_lint

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def broken_wiki(tmp_db, tmp_path):
    registry.init_db(tmp_db)
    dest = tmp_path / "broken-wiki"
    shutil.copytree(FIXTURES / "wiki-vault-broken", dest)
    # adapter normally creates these, but copytree from fixture won't:
    (dest / ".trash").mkdir(exist_ok=True)
    (dest / "raw").mkdir(exist_ok=True)
    vault = registry.add_vault(
        tmp_db, name="bw", path=dest, type_="markdown", mode="wiki"
    )
    # Hermetic mtimes: git checkout doesn't preserve mtime and copytree (copy2)
    # carries the fixture's stored mtime, so on a stale local checkout every page
    # can exceed the 7-day orphan grace and get mis-flagged. Pin all pages "now",
    # then age only the one page the orphan test expects to trip.
    now = time.time()
    for p in dest.rglob("*.md"):
        os.utime(p, (now, now))
    old = now - 30 * 86400  # 30 days old → exceeds the 7-day grace
    os.utime(dest / "wiki/summaries/orphan-summary.md", (old, old))
    reindex.full(tmp_db, vault_id=vault["id"])
    return tmp_db, vault, dest


def test_orphan_pages_detected(broken_wiki):
    db, vault, root = broken_wiki
    report = wiki_lint.check(db, vault_id=vault["id"])
    orphans = {item["relpath"] for item in report["orphan_pages"]}
    assert "wiki/summaries/orphan-summary.md" in orphans
    assert "wiki/summaries/good-summary.md" not in orphans


def test_missing_concepts_detected(broken_wiki):
    db, vault, root = broken_wiki
    report = wiki_lint.check(db, vault_id=vault["id"])
    missing = {item["title"] for item in report["missing_concepts"]}
    assert "mentioned-twice" in missing
    assert "missing-thing" not in missing


def test_existing_entity_not_flagged_as_missing(broken_wiki):
    db, vault, root = broken_wiki
    report = wiki_lint.check(db, vault_id=vault["id"])
    missing = {item["title"] for item in report["missing_concepts"]}
    assert "karpathy" not in missing
    assert "compounding" not in missing


def test_empty_data_detected(broken_wiki):
    db, vault, root = broken_wiki
    report = wiki_lint.check(db, vault_id=vault["id"])
    empty = {item["relpath"] for item in report["empty_data"]}
    assert "wiki/concepts/empty.md" in empty
    assert "wiki/summaries/good-summary.md" not in empty


def test_dangling_links_detected(broken_wiki):
    db, vault, root = broken_wiki
    report = wiki_lint.check(db, vault_id=vault["id"])
    dangling = [(d["source"], d["target"]) for d in report["dangling_links"]]
    assert ("wiki/summaries/has-dangling.md", "entities/does-not-exist.md") in dangling
    # [[karpathy]] resolves → NOT in dangling (we only check markdown links here)
    assert all(d["target"] != "karpathy" for d in report["dangling_links"])
