"""sqlite-vec vector store for wiki page embeddings (embedding/hybrid strategies).

One virtual table per registry DB, partitioned by vault_id. Graceful no-op when
sqlite-vec is not installed — callers fall back to fts. Cosine via vec0 distance."""
from __future__ import annotations

import sys
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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vec_meta("
        "  id INTEGER PRIMARY KEY CHECK(id=1), model TEXT, dim INTEGER)"
    )


def reset(db_path) -> None:
    """Drop the vector table so the next upsert recreates it (used when the
    embedding model/dim changes). No-op when sqlite-vec is unavailable."""
    if not available():
        return
    conn = _connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS vec_notes")
        conn.execute("DROP TABLE IF EXISTS vec_meta")
        conn.commit()
    finally:
        conn.close()


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
        # UPSERT meta row: single row tracks model + dim for the whole store
        model_val = getattr(embedder, "model", None)
        conn.execute(
            "INSERT INTO vec_meta(id, model, dim) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET model=excluded.model, dim=excluded.dim",
            (model_val, embedder.dim))
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def query(db_path, *, vault_id: int, embedder, text: str, limit: int = 5) -> list[dict]:
    """Return [{relpath, score}] nearest to `text` (score = 1/(1+distance), higher=better).
    Returns [] (fail-closed) when the stored model/dim differs from the embedder."""
    if not available() or embedder is None or not (text or "").strip():
        return []
    import sqlite_vec
    conn = None
    try:
        conn = _connect(db_path)
        _ensure_table(conn, embedder.dim)
        # Fail-closed: reject if dim or model differs from stored meta
        meta_row = conn.execute("SELECT model, dim FROM vec_meta WHERE id=1").fetchone()
        if meta_row is not None:
            stored_dim = meta_row["dim"]
            stored_model = meta_row["model"]
            query_model = getattr(embedder, "model", None)
            dim_mismatch = (stored_dim != embedder.dim)
            model_mismatch = (
                stored_model is not None
                and query_model is not None
                and stored_model != query_model
            )
            if dim_mismatch or model_mismatch:
                print(
                    "vector store was built with a different embedding model; "
                    "run `omw embed reindex`",
                    file=sys.stderr,
                )
                return []
        qv = embedder.embed([text])[0]
        cur = conn.execute(
            "SELECT relpath, distance FROM vec_notes "
            "WHERE vault_id = ? AND embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (vault_id, sqlite_vec.serialize_float32(qv), limit))
        return [{"relpath": r["relpath"], "score": 1.0 / (1.0 + float(r["distance"]))}
                for r in cur.fetchall()]
    except Exception as e:
        print(
            f"warning: vector query failed ({type(e).__name__}); falling back to FTS",
            file=sys.stderr,
        )
        return []
    finally:
        if conn is not None:
            conn.close()


def count(db_path, *, vault_id: int) -> int:
    """Return the number of vec_notes rows for the given vault (0 if table absent)."""
    if not available():
        return 0
    try:
        conn = _connect(db_path)
        try:
            has = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_notes'"
            ).fetchone()
            if not has:
                return 0
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM vec_notes WHERE vault_id = ?", (vault_id,)
            ).fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()
    except Exception:
        return 0


def meta(db_path) -> "dict | None":
    """Return {"model": ..., "dim": ...} from vec_meta, or None if absent/unavailable."""
    if not available():
        return None
    try:
        conn = _connect(db_path)
        try:
            has = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_meta'"
            ).fetchone()
            if not has:
                return None
            row = conn.execute("SELECT model, dim FROM vec_meta WHERE id=1").fetchone()
            if row is None:
                return None
            return {"model": row["model"], "dim": row["dim"]}
        finally:
            conn.close()
    except Exception:
        return None
