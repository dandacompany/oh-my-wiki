"""scripts/history.py — request/interaction history (deterministic).

Records each unit of work the agent completes (per vault, by request type) into
the `interactions` table, and recalls it deterministically. Distinct from
wiki/log.md (a content changelog). stdlib only; no FTS5.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts import registry

REQUEST_TYPES = ("research", "query", "generate", "edit", "fix", "ingest", "other")
OUTCOMES = ("new", "revised", "regenerated", "accepted")


class HistoryError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row(r) -> dict:
    d = dict(r)
    d["refs"] = json.loads(d.get("refs") or "[]")
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


def log(db_path, *, vault_id, request_type, request, summary=None, outcome="new",
        revises_id=None, focus=None, refs=(), tags=()) -> int:
    if request_type not in REQUEST_TYPES:
        raise HistoryError(f"unknown request_type {request_type!r}; expected one of {REQUEST_TYPES}")
    if outcome not in OUTCOMES:
        raise HistoryError(f"unknown outcome {outcome!r}; expected one of {OUTCOMES}")
    conn = registry.connect(db_path)
    try:
        if revises_id is not None:
            parent = conn.execute(
                "SELECT id FROM interactions WHERE id = ? AND vault_id = ?",
                (revises_id, vault_id)).fetchone()
            if parent is None:
                raise HistoryError(f"revises_id {revises_id} not found in this vault")
        with conn:
            cur = conn.execute(
                "INSERT INTO interactions(vault_id, created_at, request_type, request, "
                "summary, outcome, revises_id, focus, refs, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (vault_id, _now(), request_type, request, summary, outcome, revises_id, focus,
                 json.dumps(list(refs), ensure_ascii=False),
                 json.dumps(list(tags), ensure_ascii=False)))
        return cur.lastrowid
    finally:
        conn.close()


def get(db_path, *, vault_id, id_) -> dict | None:
    conn = registry.connect(db_path)
    try:
        r = conn.execute("SELECT * FROM interactions WHERE id = ? AND vault_id = ?",
                         (id_, vault_id)).fetchone()
        return _row(r) if r else None
    finally:
        conn.close()


def list_(db_path, *, vault_id, request_type=None, outcome=None, since=None,
          ref=None, limit=50) -> list[dict]:
    where = ["vault_id = ?"]
    params: list = [vault_id]
    if request_type is not None:
        where.append("request_type = ?")
        params.append(request_type)
    if outcome is not None:
        where.append("outcome = ?")
        params.append(outcome)
    if since is not None:
        where.append("created_at >= ?")
        params.append(since)
    if ref is not None:
        where.append("refs LIKE ?")
        params.append(f'%"{ref}"%')
    sql = (f"SELECT * FROM interactions WHERE {' AND '.join(where)} "
           f"ORDER BY id DESC LIMIT ?")
    params.append(limit)
    conn = registry.connect(db_path)
    try:
        return [_row(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()
