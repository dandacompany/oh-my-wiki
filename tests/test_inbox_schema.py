# tests/test_inbox_schema.py
from scripts import registry


def _columns(db, table):
    conn = registry.connect(db)
    try:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_inbox_queue_table_created(tmp_path):
    db = tmp_path / "r.db"
    registry.init_db(db)
    cols = _columns(db, "inbox_queue")
    assert {"id", "vault_id", "url", "normalized_url", "status",
            "title", "added_at", "fetched_at", "raw_relpath", "error"} <= cols


def test_inbox_queue_unique_per_vault_normalized_url(tmp_path):
    import sqlite3
    db = tmp_path / "r.db"
    registry.init_db(db)
    conn = registry.connect(db)
    try:
        # Insert a vault row so FK constraint on vault_id is satisfied.
        conn.execute(
            "INSERT INTO vaults(id, name, path, type, mode, is_active, created_at, last_used) "
            "VALUES (1, 'v', '/v', 'markdown', 'wiki', 0, 't', 't')"
        )
        conn.commit()
        conn.execute("INSERT INTO inbox_queue(vault_id, url, normalized_url, status, added_at) "
                     "VALUES (1, 'u', 'n', 'queued', 't')")
        conn.commit()
        raised = False
        try:
            conn.execute("INSERT INTO inbox_queue(vault_id, url, normalized_url, status, added_at) "
                         "VALUES (1, 'u2', 'n', 'queued', 't')")
            conn.commit()
        except sqlite3.IntegrityError:
            raised = True
        assert raised  # UNIQUE(vault_id, normalized_url)
    finally:
        conn.close()
