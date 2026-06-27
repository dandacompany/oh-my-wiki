# tests/test_fts.py
from scripts import fts, registry


def _conn(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    return registry.connect(db), db


def test_fts5_available_here():
    assert fts.fts5_available() is True


def test_index_and_search_body_only_term(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/a.md", title="Alpha",
                   summary="s", tags=["x"], body="the quick brown fox")
    conn.commit(); conn.close()
    hits = fts.search(db, vault_id=1, query="fox", limit=5)  # 'fox' only in body
    assert [h["relpath"] for h in hits] == ["wiki/a.md"]


def test_bm25_title_outranks_body(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/title.md", title="fox", summary="",
                   tags=[], body="unrelated")
    fts.index_note(conn, vault_id=1, relpath="wiki/body.md", title="other", summary="",
                   tags=[], body="a fox ran")
    conn.commit(); conn.close()
    hits = fts.search(db, vault_id=1, query="fox", limit=5)
    assert hits[0]["relpath"] == "wiki/title.md"


def test_search_special_chars_do_not_raise(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/a.md", title="t", summary="",
                   tags=[], body="alpha beta")
    conn.commit(); conn.close()
    for q in ['foo*', 'a AND b', '"quote', 'NEAR(x)', ':::']:
        assert fts.search(db, vault_id=1, query=q, limit=5) is not None  # [] or rows, never raises


def test_index_note_idempotent(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    for _ in range(2):
        fts.index_note(conn, vault_id=1, relpath="wiki/a.md", title="t", summary="",
                       tags=[], body="alpha")
    conn.commit()
    n = conn.execute("SELECT count(*) FROM notes_fts WHERE relpath='wiki/a.md'").fetchone()[0]
    conn.close()
    assert n == 1


def test_search_returns_none_when_vault_unindexed(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)  # table exists but empty
    conn.commit(); conn.close()
    assert fts.search(db, vault_id=1, query="anything", limit=5) is None


def test_body_josa_form_found_by_bare_noun(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/k.md", title="제목",
                   summary="", tags=[], body="학교에서 배웠다")
    conn.commit(); conn.close()
    hits = fts.search(db, vault_id=1, query="학교", limit=5)  # bare noun, body has 학교에서
    assert [h["relpath"] for h in hits] == ["wiki/k.md"]


def test_query_with_josa_also_matches(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/k.md", title="t",
                   summary="", tags=[], body="학교 정문")
    conn.commit(); conn.close()
    hits = fts.search(db, vault_id=1, query="학교에서", limit=5)  # josa on the query
    assert [h["relpath"] for h in hits] == ["wiki/k.md"]
