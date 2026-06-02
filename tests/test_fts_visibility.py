# tests/test_fts_visibility.py
from scripts import fts, registry


def _conn(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    return registry.connect(db), db


def _fts_columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(notes_fts)")}


def test_ensure_fts_creates_visibility_column(tmp_path):
    conn, db = _conn(tmp_path)
    migrated = fts.ensure_fts(conn)
    assert "visibility" in _fts_columns(conn)
    assert migrated is False  # fresh create is not a migration
    conn.close()


def test_ensure_fts_migrates_old_shape(tmp_path):
    conn, db = _conn(tmp_path)
    # Build an OLD-shape notes_fts (no visibility column) directly.
    conn.execute(
        "CREATE VIRTUAL TABLE notes_fts USING fts5("
        "relpath, title, summary, tags, body, vault_id UNINDEXED, tokenize='unicode61')")
    conn.execute(
        "INSERT INTO notes_fts(relpath, title, summary, tags, body, vault_id) "
        "VALUES ('wiki/a.md','A','','','body','1')")
    conn.commit()
    migrated = fts.ensure_fts(conn)
    assert migrated is True
    assert "visibility" in _fts_columns(conn)
    # old rows are gone (table was rebuilt); caller must full-reindex
    assert conn.execute("SELECT count(*) FROM notes_fts").fetchone()[0] == 0
    conn.close()


def test_ensure_fts_second_call_is_noop_after_migration(tmp_path):
    conn, db = _conn(tmp_path)
    # old-shape table (no visibility column)
    conn.execute(
        "CREATE VIRTUAL TABLE notes_fts USING fts5("
        "relpath, title, summary, tags, body, vault_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    assert fts.ensure_fts(conn) is True   # first call migrates (drops + recreates)
    # populate a row, then call ensure_fts AGAIN — it must NOT re-drop
    fts.index_note(conn, vault_id=1, relpath="wiki/a.md", title="t",
                   summary="", tags=[], body="b", visibility="public")
    conn.commit()
    assert fts.ensure_fts(conn) is False  # already has visibility col → no-op
    assert conn.execute("SELECT count(*) FROM notes_fts").fetchone()[0] == 1  # data intact
    conn.close()


def test_index_note_stores_visibility_and_search_filters(tmp_path):
    conn, db = _conn(tmp_path)
    fts.ensure_fts(conn)
    fts.index_note(conn, vault_id=1, relpath="wiki/pub.md", title="fox",
                   summary="", tags=[], body="public body", visibility="public")
    fts.index_note(conn, vault_id=1, relpath="wiki/priv.md", title="fox",
                   summary="", tags=[], body="private body", visibility="private")
    conn.commit()
    conn.close()
    all_hits = fts.search(db, vault_id=1, query="fox", limit=5)
    pub_only = fts.search(db, vault_id=1, query="fox", limit=5, visibility="public")
    assert {h["relpath"] for h in all_hits} == {"wiki/pub.md", "wiki/priv.md"}
    assert {h["relpath"] for h in pub_only} == {"wiki/pub.md"}
