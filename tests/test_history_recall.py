from scripts import history


def _vault(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    return make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})


def test_similar_ranks_overlap(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    history.log(db, vault_id=vid, request_type="generate", request="make a chalkboard slide about agents")
    history.log(db, vault_id=vid, request_type="query", request="what is the weather")
    hits = history.similar(db, vault_id=vid, text="make a slide about agents")
    assert hits and hits[0]["request"].startswith("make a chalkboard slide")
    assert all(h["score"] > 0 for h in hits)
    assert "what is the weather" not in [h["request"] for h in hits]


def test_similar_respects_type_filter(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    history.log(db, vault_id=vid, request_type="generate", request="slide about agents")
    history.log(db, vault_id=vid, request_type="research", request="research about agents")
    hits = history.similar(db, vault_id=vid, text="agents", request_type="research")
    assert [h["request_type"] for h in hits] == ["research"]


def test_find_matches_focus(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    base = history.log(db, vault_id=vid, request_type="generate", request="draft email")
    history.log(db, vault_id=vid, request_type="edit", request="redo", outcome="revised",
                revises_id=base, focus="톤을 더 정중하게")
    assert [r["focus"] for r in history.find(db, vault_id=vid, query="정중하게")] == ["톤을 더 정중하게"]


def test_prefs_aggregates_revision_focus_only(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    base = history.log(db, vault_id=vid, request_type="generate", request="draft", focus="ignored")
    history.log(db, vault_id=vid, request_type="edit", request="r1", outcome="revised",
                revises_id=base, focus="톤을 정중하게 바꿔줘")
    history.log(db, vault_id=vid, request_type="edit", request="r2", outcome="regenerated",
                revises_id=base, focus="톤이 너무 딱딱해 정중하게")
    p = history.prefs(db, vault_id=vid)
    assert p["revisions"] == 2                      # only revised+regenerated rows
    terms = dict(p["focus_terms"])
    assert terms.get("정중하게", 0) >= 2            # recurring focus term surfaced
    assert len(p["recent"]) == 2
    # a 'new' row's focus must NOT contribute
    assert "ignored" not in [t for t, _ in p["focus_terms"]]
