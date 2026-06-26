import pytest

from scripts import history


def _vault(tmp_path, monkeypatch):
    from tests.conftest import make_vault_with_pages
    return make_vault_with_pages(tmp_path, monkeypatch, pages={"raw/a.md": "# A\n\nx"})


def test_log_and_get_roundtrip(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    i = history.log(db, vault_id=vid, request_type="generate", request="make a slide",
                    summary="made 1 slide", refs=["wiki/concepts/agents.md"], tags=["slide"])
    row = history.get(db, vault_id=vid, id_=i)
    assert row["request_type"] == "generate"
    assert row["request"] == "make a slide"
    assert row["outcome"] == "new"
    assert row["refs"] == ["wiki/concepts/agents.md"]   # decoded JSON
    assert row["tags"] == ["slide"]


def test_log_rejects_bad_enum(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    with pytest.raises(history.HistoryError):
        history.log(db, vault_id=vid, request_type="nope", request="x")
    with pytest.raises(history.HistoryError):
        history.log(db, vault_id=vid, request_type="query", request="x", outcome="bogus")


def test_log_revises_must_exist_in_vault(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    with pytest.raises(history.HistoryError):
        history.log(db, vault_id=vid, request_type="edit", request="x",
                    outcome="revised", revises_id=999)
    base = history.log(db, vault_id=vid, request_type="generate", request="orig")
    rev = history.log(db, vault_id=vid, request_type="edit", request="shorter",
                      outcome="revised", revises_id=base, focus="너무 길어 줄여줘")
    assert history.get(db, vault_id=vid, id_=rev)["revises_id"] == base


def test_list_facets_and_vault_scope(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    history.log(db, vault_id=vid, request_type="research", request="r1")
    history.log(db, vault_id=vid, request_type="query", request="q1")
    assert len(history.list_(db, vault_id=vid)) == 2
    assert [r["request"] for r in history.list_(db, vault_id=vid, request_type="research")] == ["r1"]
    # other vault sees nothing
    from scripts import registry
    v2 = registry.add_vault(db, name="other", path=tmp_path / "v2", type_="markdown", mode="wiki")
    assert history.list_(db, vault_id=v2["id"]) == []


def test_fk_cascade_on_vault_delete(tmp_path, monkeypatch):
    db, vid = _vault(tmp_path, monkeypatch)
    history.log(db, vault_id=vid, request_type="query", request="q1")
    from scripts import registry
    registry.forget_vault(db, "default")   # DELETE FROM vaults → cascade
    conn = registry.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM interactions WHERE vault_id=?", (vid,)).fetchone()["n"]
    finally:
        conn.close()
    assert n == 0
