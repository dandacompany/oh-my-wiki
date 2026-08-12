"""sqlite-vec vector store for wiki page embeddings (embedding/hybrid strategies).

One virtual table per registry DB, partitioned by vault_id. Graceful no-op when
sqlite-vec is not installed — callers fall back to fts. Cosine via vec0 distance."""
from __future__ import annotations

import sys
from pathlib import Path

from scripts import embed, registry


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


def _ensure_meta_table(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vec_meta("
        "  id INTEGER PRIMARY KEY CHECK(id=1), model TEXT, dim INTEGER, "
        "  prefix_scheme TEXT NOT NULL DEFAULT 'none', "
        "  fingerprint TEXT NOT NULL DEFAULT '', "
        "  distance_metric TEXT NOT NULL DEFAULT 'cosine')"
    )
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(vec_meta)")}
    if "prefix_scheme" not in cols:
        conn.execute(
            "ALTER TABLE vec_meta ADD COLUMN prefix_scheme TEXT NOT NULL DEFAULT 'none'"
        )
    if "fingerprint" not in cols:
        conn.execute(
            "ALTER TABLE vec_meta ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"
        )
    if "distance_metric" not in cols:
        # Existing vec_notes tables were created without a metric declaration,
        # which means sqlite-vec's default L2 distance.  Mark them unknown so
        # query/upsert fail closed until `omw embed reindex` recreates the table.
        conn.execute(
            "ALTER TABLE vec_meta ADD COLUMN distance_metric TEXT NOT NULL DEFAULT 'unknown'"
        )


def _ensure_table(conn, dim: int) -> None:
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_notes USING vec0("
        f"  relpath TEXT, vault_id INTEGER, "
        f"  embedding FLOAT[{dim}] distance_metric=cosine)"
    )
    _ensure_meta_table(conn)


def _table_uses_cosine(conn) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='vec_notes'"
    ).fetchone()
    sql = (row["sql"] if row else "") or ""
    return "distance_metric=cosine" in sql.replace(" ", "").lower()


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
    texts = embed.passage_texts(embedder, [t for _, t in rows])
    vecs = embedder.embed(texts)
    conn = _connect(db_path)
    try:
        _ensure_table(conn, embedder.dim)
        if not _table_uses_cosine(conn):
            raise RuntimeError(
                "vector store uses the legacy L2 distance; run `omw embed reindex`"
            )
        for (relpath, _), v in zip(rows, vecs):
            conn.execute("DELETE FROM vec_notes WHERE vault_id = ? AND relpath = ?",
                         (vault_id, relpath))
            conn.execute(
                "INSERT INTO vec_notes(relpath, vault_id, embedding) VALUES (?, ?, ?)",
                (relpath, vault_id, sqlite_vec.serialize_float32(v)))
        # UPSERT meta row: single row tracks model + dim for the whole store
        model_val = getattr(embedder, "model", None)
        scheme = embed.prefix_scheme(embedder)
        fingerprint = embed.embedding_fingerprint(embedder)
        conn.execute(
            "INSERT INTO vec_meta(id, model, dim, prefix_scheme, fingerprint, distance_metric) "
            "VALUES (1, ?, ?, ?, ?, 'cosine')"
            " ON CONFLICT(id) DO UPDATE SET model=excluded.model, dim=excluded.dim, "
            "prefix_scheme=excluded.prefix_scheme, fingerprint=excluded.fingerprint, "
            "distance_metric=excluded.distance_metric",
            (model_val, embedder.dim, scheme, fingerprint))
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def query(db_path, *, vault_id: int, embedder, text: str, limit: int = 5) -> list[dict]:
    """Return [{relpath, score}] nearest to `text` (score = 1/(1+distance), higher=better).
    Returns [] (fail-closed) when the stored model/dim differs from the embedder."""
    if not available() or embedder is None or not (text or "").strip():
        return []
    conn = None
    try:
        import sqlite_vec  # inside try: an import failure here also falls back to FTS
        conn = _connect(db_path)
        _ensure_table(conn, embedder.dim)
        if not _table_uses_cosine(conn):
            print(
                "vector store uses the legacy L2 distance; run `omw embed reindex`",
                file=sys.stderr,
            )
            return []
        # Fail-closed: reject if dim or model differs from stored meta
        meta_row = conn.execute(
            "SELECT model, dim, prefix_scheme, fingerprint, distance_metric "
            "FROM vec_meta WHERE id=1"
        ).fetchone()
        if meta_row is not None:
            stored_dim = meta_row["dim"]
            stored_model = meta_row["model"]
            query_model = getattr(embedder, "model", None)
            stored_scheme = meta_row["prefix_scheme"] or "none"
            query_scheme = embed.prefix_scheme(embedder)
            stored_fingerprint = meta_row["fingerprint"] or ""
            query_fingerprint = embed.embedding_fingerprint(embedder)
            stored_metric = meta_row["distance_metric"] or "unknown"
            dim_mismatch = (stored_dim != embedder.dim)
            model_mismatch = (
                stored_model is not None
                and query_model is not None
                and stored_model != query_model
            )
            scheme_mismatch = stored_scheme != query_scheme
            fingerprint_mismatch = stored_fingerprint != query_fingerprint
            metric_mismatch = stored_metric != "cosine"
            if (dim_mismatch or model_mismatch or scheme_mismatch
                    or fingerprint_mismatch or metric_mismatch):
                print(
                    "vector store was built with a different embedding model or "
                    "runtime contract; "
                    "run `omw embed reindex`",
                    file=sys.stderr,
                )
                return []
        qv = embedder.embed([embed.query_text(embedder, text)])[0]
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
    """Return the vector runtime contract from vec_meta, or None if unavailable."""
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
            _ensure_meta_table(conn)
            row = conn.execute(
                "SELECT model, dim, prefix_scheme, fingerprint, distance_metric "
                "FROM vec_meta WHERE id=1"
            ).fetchone()
            if row is None:
                return None
            return {"model": row["model"], "dim": row["dim"],
                    "prefix_scheme": row["prefix_scheme"] or "none",
                    "fingerprint": row["fingerprint"] or "",
                    "distance_metric": row["distance_metric"] or "unknown"}
        finally:
            conn.close()
    except Exception:
        return None
