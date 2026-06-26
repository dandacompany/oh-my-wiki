"""scripts/history.py — request/interaction history (deterministic).

Records each unit of work the agent completes (per vault, by request type) into
the `interactions` table, and recalls it deterministically. Distinct from
wiki/log.md (a content changelog). stdlib only; no FTS5.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone

from scripts import registry

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)

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


#: tiny stoplist so prefs surfaces content words, not particles/fillers.
_STOPLIST = {
    "the", "a", "an", "to", "of", "and", "or", "for", "is", "it", "this", "that",
    "을", "를", "이", "가", "은", "는", "에", "의", "로", "으로", "도", "좀", "더",
    "것", "수", "그", "저", "해", "해줘", "바꿔줘", "바꿔", "줘",
}


def _tokens(text) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def similar(db_path, *, vault_id, text, limit=8, request_type=None) -> list[dict]:
    q = _tokens(text)
    if not q:
        return []
    rows = list_(db_path, vault_id=vault_id, request_type=request_type, limit=10_000)
    scored = []
    for r in rows:
        toks = _tokens(f"{r['request']} {r.get('summary') or ''}")
        score = len(q & toks)
        if score > 0:
            scored.append({**r, "score": score})
    scored.sort(key=lambda r: (-r["score"], -r["id"]))
    return scored[:limit]


def find(db_path, *, vault_id, query, limit=10) -> list[dict]:
    q = _tokens(query)
    if not q:
        return []
    out = []
    for r in list_(db_path, vault_id=vault_id, limit=10_000):
        toks = _tokens(f"{r['request']} {r.get('summary') or ''} {r.get('focus') or ''}")
        if q & toks:
            out.append(r)
        if len(out) >= limit:
            break
    return out


def prefs(db_path, *, vault_id, request_type=None, limit=10) -> dict:
    conn = registry.connect(db_path)
    try:
        where = ["vault_id = ?", "outcome IN ('revised', 'regenerated')", "focus IS NOT NULL"]
        params: list = [vault_id]
        if request_type is not None:
            where.append("request_type = ?")
            params.append(request_type)
        rows = conn.execute(
            f"SELECT focus FROM interactions WHERE {' AND '.join(where)} ORDER BY id DESC",
            params).fetchall()
    finally:
        conn.close()
    counter: Counter = Counter()
    recent: list[str] = []
    for r in rows:
        focus = r["focus"]
        if not focus:
            continue
        recent.append(focus)
        for t in _tokens(focus):
            if t not in _STOPLIST and len(t) > 1:
                counter[t] += 1
    return {"revisions": len(rows), "focus_terms": counter.most_common(limit),
            "recent": recent[:5]}
