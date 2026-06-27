"""SQLite FTS5 full-text index for wiki pages (optional; auto-detected).

A standalone FTS5 virtual table (notes_fts) populated during reindex. Created in
CODE (not schema.sql) so init_db never breaks on a sqlite build lacking FTS5.
search_index falls back to the token scorer when FTS5 is unavailable.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from scripts import registry, text_normalize

_FTS5_AVAILABLE: bool | None = None
_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)


def fts5_available() -> bool:
    global _FTS5_AVAILABLE
    if _FTS5_AVAILABLE is None:
        try:
            c = sqlite3.connect(":memory:")
            c.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
            c.close()
            _FTS5_AVAILABLE = True
        except sqlite3.OperationalError:
            _FTS5_AVAILABLE = False
    return _FTS5_AVAILABLE


def _read_analyzer_ver(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fts_meta'"
    ).fetchone()
    if not row:
        return None
    r = conn.execute("SELECT analyzer_ver FROM fts_meta LIMIT 1").fetchone()
    return r[0] if r else None


def _write_analyzer_ver(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS fts_meta (analyzer_ver TEXT)")
    conn.execute("DELETE FROM fts_meta")
    conn.execute("INSERT INTO fts_meta(analyzer_ver) VALUES (?)",
                 (text_normalize.ANALYZER_VERSION,))


def ensure_fts(conn: sqlite3.Connection) -> bool:
    """Ensure notes_fts exists with a visibility column AND matches the current
    analyzer version. Returns True if it (re)built the table — the caller must
    then full-reindex to repopulate."""
    rebuilt = False
    existing = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='notes_fts'"
    ).fetchone()
    if existing:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(notes_fts)")}
        stale_shape = "visibility" not in cols
        stale_analyzer = _read_analyzer_ver(conn) != text_normalize.ANALYZER_VERSION
        if not stale_shape and not stale_analyzer:
            return False
        conn.execute("DROP TABLE notes_fts")  # FTS5 has no ALTER ADD COLUMN
        _create_fts(conn)
        _write_analyzer_ver(conn)
        return True
    _create_fts(conn)
    _write_analyzer_ver(conn)
    return rebuilt


def _create_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5("
        "relpath, title, summary, tags, body, "
        "vault_id UNINDEXED, visibility UNINDEXED, "
        "tokenize='unicode61')"
    )


def clear_vault(conn: sqlite3.Connection, *, vault_id: int) -> None:
    conn.execute("DELETE FROM notes_fts WHERE vault_id = ?", (str(vault_id),))


def index_note(conn: sqlite3.Connection, *, vault_id: int, relpath: str,
               title, summary, tags, body, visibility: str = "private") -> None:
    conn.execute("DELETE FROM notes_fts WHERE vault_id = ? AND relpath = ?",
                 (str(vault_id), relpath))
    conn.execute(
        "INSERT INTO notes_fts(relpath, title, summary, tags, body, vault_id, visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (relpath,
         text_normalize.normalize_text(title or ""),
         text_normalize.normalize_text(summary or ""),
         text_normalize.normalize_text(" ".join(tags or [])),
         text_normalize.normalize_text(body or ""),
         str(vault_id),
         visibility if visibility in ("public", "private") else "private"),
    )


def _match_query(query: str) -> str:
    """Build a safe FTS5 MATCH expression: josa-normalize, quote each token, OR-join.
    Quoting neutralizes FTS5 operators (*, :, AND, NEAR, quotes) so user input never raises."""
    toks = _TOKEN_RE.findall(text_normalize.normalize_text(query or ""))
    return " OR ".join(f'"{t}"' for t in toks)


def search(db_path: Path, *, vault_id: int, query: str, limit: int,
           visibility: str | None = None):
    """FTS5 BM25 search. Returns a list of hit dicts, [] for no match, or
    None when the vault isn't indexed yet (caller should fall back).
    When visibility='public', only public rows are returned."""
    match = _match_query(query)
    conn = registry.connect(db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='notes_fts'"
        ).fetchone()
        if not exists:
            return None
        has_rows = conn.execute(
            "SELECT 1 FROM notes_fts WHERE vault_id = ? LIMIT 1", (str(vault_id),)
        ).fetchone()
        if not has_rows:
            return None  # vault not indexed → fall back
        if not match:
            return []
        sql = ("SELECT relpath, title, summary, tags, bm25(notes_fts) AS rank "
               "FROM notes_fts WHERE notes_fts MATCH ? AND vault_id = ?")
        params: list = [match, str(vault_id)]
        if visibility == "public":
            sql += " AND visibility = 'public'"
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        rows = list(conn.execute(sql, params))
        return [{
            "relpath": r["relpath"],
            "title": r["title"] or None,
            "summary": r["summary"] or None,
            "tags": r["tags"].split() if r["tags"] else [],
            "score": round(-r["rank"], 3),  # bm25: lower = better; negate so higher = better
        } for r in rows]
    finally:
        conn.close()
