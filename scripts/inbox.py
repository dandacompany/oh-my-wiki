"""URL inbox queue: deterministic CRUD over inbox_queue + batch run."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import fetch, ingest, reindex, registry, urls


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(db_path: Path, *, vault_id: int, url: str) -> dict:
    """Queue a URL (dedup by normalized form). Returns the row dict (+ 'deduped')."""
    norm = urls.normalize_url(url)
    conn = registry.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT * FROM inbox_queue WHERE vault_id = ? AND normalized_url = ?",
            (vault_id, norm),
        ).fetchone()
        if existing:
            return {**dict(existing), "deduped": True}
        with conn:
            cur = conn.execute(
                "INSERT INTO inbox_queue(vault_id, url, normalized_url, status, added_at) "
                "VALUES (?, ?, ?, 'queued', ?)",
                (vault_id, url, norm, _now()),
            )
            row = conn.execute(
                "SELECT * FROM inbox_queue WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
        return {**dict(row), "deduped": False}
    finally:
        conn.close()


def list_items(db_path: Path, *, vault_id: int, status: str | None = None) -> list[dict]:
    """Return all inbox rows for a vault, optionally filtered by status."""
    conn = registry.connect(db_path)
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM inbox_queue WHERE vault_id = ? AND status = ? ORDER BY id",
                (vault_id, status),
            )
        else:
            rows = conn.execute(
                "SELECT * FROM inbox_queue WHERE vault_id = ? ORDER BY id",
                (vault_id,),
            )
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove(db_path: Path, *, vault_id: int, url: str) -> int:
    """Remove a queued URL by its normalized value. Returns rows deleted."""
    norm = urls.normalize_url(url)
    conn = registry.connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM inbox_queue WHERE vault_id = ? AND normalized_url = ?",
                (vault_id, norm),
            )
        return cur.rowcount
    finally:
        conn.close()


def retry(db_path: Path, *, vault_id: int) -> int:
    """Reset all failed items back to queued. Returns the number reset."""
    conn = registry.connect(db_path)
    try:
        cur = conn.execute(
            "UPDATE inbox_queue SET status='queued', error=NULL "
            "WHERE vault_id = ? AND status = 'failed'", (vault_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def clear(db_path: Path, *, vault_id: int) -> int:
    """Delete all inbox rows for a vault. Returns rows deleted."""
    conn = registry.connect(db_path)
    try:
        with conn:
            cur = conn.execute(
                "DELETE FROM inbox_queue WHERE vault_id = ?",
                (vault_id,),
            )
        return cur.rowcount
    finally:
        conn.close()


def _set_status(conn, item_id, status, *, raw_relpath=None, error=None, title=None):
    conn.execute(
        "UPDATE inbox_queue SET status = ?, fetched_at = ?, raw_relpath = ?, "
        "error = ?, title = COALESCE(?, title) WHERE id = ?",
        (status, _now(), raw_relpath, error, title, item_id),
    )


def run(db_path: Path, *, vault_id: int, today: str, html_backend: str = "auto") -> dict:
    """Fetch every queued item → save raw → mark fetched/failed. Deterministic;
    summary/entity synthesis is left to the `ingest` LLM flow. Partial failures
    are isolated (one bad URL never aborts the batch)."""
    queued = list_items(db_path, vault_id=vault_id, status="queued")
    fetched, failed = [], []
    for item in queued:
        try:
            res = fetch.fetch_url(item["url"], html_backend=html_backend)
            relpath = ingest.save_raw(
                db_path, vault_id=vault_id, content=res["text"], ext="md",
                title=res["title"] or item["url"], date_str=today,
            )
            conn = registry.connect(db_path)
            try:
                with conn:
                    _set_status(conn, item["id"], "fetched",
                                raw_relpath=relpath, title=res["title"])
            finally:
                conn.close()
            fetched.append({"url": item["url"], "raw_relpath": relpath,
                            "backend": res["backend"]})
        except Exception as exc:
            conn = registry.connect(db_path)
            try:
                with conn:
                    _set_status(conn, item["id"], "failed", error=str(exc)[:300])
            finally:
                conn.close()
            failed.append({"url": item["url"], "error": str(exc)[:300]})
    if fetched:
        reindex.incremental(db_path, vault_id=vault_id)
    return {"fetched": fetched, "failed": failed, "queued_count": len(queued)}
