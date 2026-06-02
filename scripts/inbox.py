"""URL inbox queue: deterministic CRUD over inbox_queue (run batch added later)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import registry, urls


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
