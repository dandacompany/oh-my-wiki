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
