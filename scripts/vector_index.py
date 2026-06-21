"""sqlite-vec vector store for wiki page embeddings (embedding/hybrid strategies).

One virtual table per registry DB, partitioned by vault_id. Graceful no-op when
sqlite-vec is not installed — callers fall back to fts. Cosine via vec0 distance."""
from __future__ import annotations

from pathlib import Path

from scripts import registry


def available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
        return True
    except Exception:
        return False


def _connect(db_path: Path):
    conn = registry.connect(db_path)
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _ensure_table(conn, dim: int) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_notes USING vec0("
        f"  relpath TEXT, vault_id INTEGER, embedding FLOAT[{dim}])"
    )


def upsert(db_path, *, vault_id: int, embedder, rows) -> int:
    """Embed and store (relpath, text) rows for a vault. Returns count stored."""
    if not available() or embedder is None or not rows:
        return 0
    import sqlite_vec
    texts = [t for _, t in rows]
    vecs = embedder.embed(texts)
    conn = _connect(db_path)
    try:
        _ensure_table(conn, embedder.dim)
        for (relpath, _), v in zip(rows, vecs):
            conn.execute("DELETE FROM vec_notes WHERE vault_id = ? AND relpath = ?",
                         (vault_id, relpath))
            conn.execute(
                "INSERT INTO vec_notes(relpath, vault_id, embedding) VALUES (?, ?, ?)",
                (relpath, vault_id, sqlite_vec.serialize_float32(v)))
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def query(db_path, *, vault_id: int, embedder, text: str, limit: int = 5) -> list[dict]:
    """Return [{relpath, score}] nearest to `text` (score = 1/(1+distance), higher=better)."""
    if not available() or embedder is None or not (text or "").strip():
        return []
    import sqlite_vec
    qv = embedder.embed([text])[0]
    conn = _connect(db_path)
    try:
        _ensure_table(conn, embedder.dim)
        cur = conn.execute(
            "SELECT relpath, distance FROM vec_notes "
            "WHERE vault_id = ? AND embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (vault_id, sqlite_vec.serialize_float32(qv), limit))
        return [{"relpath": r["relpath"], "score": 1.0 / (1.0 + float(r["distance"]))}
                for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()
