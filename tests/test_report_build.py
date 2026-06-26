from scripts import report


def test_grade_good_fair_needswork():
    assert report._grade(0, 0, 0, 0, 0, 0)["grade"] == "GOOD"
    assert report._grade(1, 0, 0, 0, 0, 0)["grade"] == "FAIR"
    # parse errors force NEEDS WORK regardless of issue count
    assert report._grade(0, 0, 0, 0, 0, 1)["grade"] == "NEEDS WORK"
    # issues above threshold → NEEDS WORK
    big = report._GRADE_THRESHOLD + 1
    assert report._grade(big, 0, 0, 0, 0, 0)["grade"] == "NEEDS WORK"


def test_grade_score_monotonic():
    assert report._grade(0, 0, 0, 0, 0, 0)["score"] == 100
    assert report._grade(2, 0, 0, 0, 0, 0)["score"] < 100


def test_build_seeded_vault(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "raw/src.md": "# Src\n\ncollected source.",
        "wiki/entities/alice.md": "---\ntags: [ai]\n---\n# Alice\n\nSees [[bob]].",
        "wiki/concepts/agents.md": "---\ntags: [ai, llm]\n---\n# Agents\n\nlinks [[alice]].",
        "wiki/index.md": "# Index\n\n- [[alice]]",
    })
    data = report.build(db, vid, today="2026-06-26")
    assert data["generated_at"] == "2026-06-26"
    assert data["vaults"]["total"] == 1
    assert data["vaults"]["active"] == "default"
    av = data["active_vault"]
    assert av is not None
    assert av["layers"]["raw"] == 1
    assert av["wiki"]["entities"] == 1
    assert av["wiki"]["concepts"] == 1
    assert av["wiki"]["syntheses"] == 0
    assert av["graph"]["dangling"] >= 1     # [[bob]] is unresolved
    assert av["tags"]["distinct"] >= 2      # ai, llm
    assert av["index"]["present"] is True
    assert "grade" in data["health"]["vault"]
    assert isinstance(data["next"], list)
    assert data["health"]["install"] is not None


def test_build_empty_vault_is_good(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={})
    data = report.build(db, vid, today="2026-06-26")
    assert data["active_vault"]["layers"] == {} or all(
        v == 0 for v in data["active_vault"]["layers"].values())
    assert data["health"]["vault"]["grade"] == "GOOD"


def test_build_no_active_vault(tmp_path, monkeypatch):
    omw_home = tmp_path / ".omw"
    (omw_home / "vaults").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OMW_HOME", str(omw_home))
    from scripts import registry
    registry.init_db(omw_home / "registry.db")
    data = report.build(omw_home / "registry.db", None, today="2026-06-26")
    assert data["vaults"]["total"] == 0
    assert data["active_vault"] is None
    assert data["next"] == []


def test_grade_threshold_boundary_is_fair():
    at = report._GRADE_THRESHOLD
    assert report._grade(at, 0, 0, 0, 0, 0)["grade"] == "FAIR"
    assert report._grade(at + 1, 0, 0, 0, 0, 0)["grade"] == "NEEDS WORK"


def test_build_no_reindex_skips_reindex(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})
    calls = []
    import scripts.reindex as _ri
    monkeypatch.setattr(_ri, "incremental", lambda *a, **k: calls.append(1))
    report.build(db, vid, today="2026-06-26", no_reindex=True)
    assert calls == []
    report.build(db, vid, today="2026-06-26", no_reindex=False)
    assert calls == [1]


def test_vault_health_counts_match_wiki_lint(tmp_path, monkeypatch):
    import os
    import time

    from tests.conftest import make_vault_with_pages
    from scripts import wiki_lint
    # Fixture design:
    #  - orphan_pages: wiki/entities/lonely.md has zero inbound links. We backdate
    #    its mtime past ORPHAN_GRACE_DAYS (7) so it clears the grace window.
    #  - missing_concepts: [[ghost]] is referenced from TWO distinct pages
    #    (alice.md and bob.md) and has NO page under wiki/entities|concepts,
    #    so it meets _missing_concepts' threshold=2.
    db, vid = make_vault_with_pages(tmp_path, monkeypatch, pages={
        "wiki/entities/alice.md": "# Alice\n\nrefs [[bob]] and [[ghost]].",
        "wiki/entities/bob.md": "# Bob\n\nrefs [[alice]] and [[ghost]].",
        "wiki/entities/lonely.md": "# Lonely\n\nnobody links here.",
        "wiki/index.md": "# Index\n\n- [[alice]]\n- [[bob]]",
    })
    # Backdate the orphan well past the 7-day grace window.
    old = time.time() - (wiki_lint.ORPHAN_GRACE_DAYS + 30) * 86400
    lonely = tmp_path / "vault" / "wiki" / "entities" / "lonely.md"
    os.utime(lonely, (old, old))

    lint = wiki_lint.check(db, vault_id=vid)
    expected_other = sum(len(lint.get(k) or []) for k in
                         ("missing_concepts", "contradiction_candidates",
                          "stale_claim_candidates"))
    # Verify the fixture really triggers both classes (guards against a test
    # that vacuously asserts 0).
    assert len(lint.get("orphan_pages") or []) >= 1
    assert expected_other >= 1

    vh = report.build(db, vid, today="2026-06-26", no_reindex=True)["health"]["vault"]
    assert vh["orphans"] == len(lint.get("orphan_pages") or [])
    assert vh["dangling"] == len(lint.get("dangling_links") or [])
    # On the OLD code this would be wrongly clamped/dropped (over-subtraction).
    assert vh["lint_issues"] == expected_other
