"""Weighted natural-language search over the sqlite notes index."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from scripts import fts, registry

WEIGHTS = {
    "title": 5.0,
    "tag": 3.0,
    "summary": 1.5,
    "relpath": 1.0,
}

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def query(
    db_path: Path,
    *,
    vault_id: int,
    query: str,
    limit: int = 5,
    visibility: str | None = None,
) -> list[dict]:
    """Return top-N hits as dicts {relpath, title, summary, tags, score}.
    When visibility='public', only public pages are returned (used by `omw serve`)."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    if fts.fts5_available():
        hits = fts.search(db_path, vault_id=vault_id, query=query, limit=limit,
                          visibility=visibility)
        if hits is not None:
            return hits
    # else / not-indexed → token-weighted fallback below

    conn = registry.connect(db_path)
    try:
        sql = ("SELECT id, relpath, title, summary FROM notes "
               "WHERE vault_id = ? AND parse_error = 0")
        params: list = [vault_id]
        if visibility == "public":
            sql += " AND visibility = 'public'"
        notes = list(conn.execute(sql, params))
        tags_by_id: dict[int, list[str]] = {}
        for row in conn.execute(
            """
            SELECT n.id, t.name FROM notes n
            JOIN note_tags nt ON nt.note_id = n.id
            JOIN tags t ON t.id = nt.tag_id
            WHERE n.vault_id = ?
            """,
            (vault_id,),
        ):
            tags_by_id.setdefault(row["id"], []).append(row["name"])
    finally:
        conn.close()

    scored: list[tuple[float, dict]] = []
    for note in notes:
        tags = tags_by_id.get(note["id"], [])
        score = _score(q_tokens, note, tags)
        if score > 0:
            scored.append((score, {
                "relpath": note["relpath"],
                "title": note["title"],
                "summary": note["summary"],
                "tags": tags,
                "score": round(score, 3),
            }))
    scored.sort(key=lambda x: -x[0])
    return [hit for _, hit in scored[:limit]]


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score(item) = Σ 1/(k + rank). Returns sorted desc."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def search_strategy(db_path, *, vault_id, q, limit, strategy,
                    embedder=None, visibility=None, fts_query=None):
    """fts → existing query(); embedding → vector store; hybrid → RRF(fts, embedding).
    Falls back to fts when embedding unusable."""
    fts_hits = query(db_path, vault_id=vault_id, query=(fts_query or q), limit=limit,
                     visibility=visibility)
    if strategy == "fts" or embedder is None:
        return fts_hits
    from scripts import vector_index
    emb_hits = vector_index.query(db_path, vault_id=vault_id, embedder=embedder,
                                  text=q, limit=limit)
    if strategy == "embedding":
        return emb_hits or fts_hits
    fused = rrf_fuse([[h["relpath"] for h in fts_hits],
                      [h["relpath"] for h in emb_hits]])
    meta = {h["relpath"]: h for h in (fts_hits + emb_hits)}
    out = []
    for relpath, score in fused[:limit]:
        row = dict(meta.get(relpath, {"relpath": relpath}))
        row["score"] = round(score, 4)
        out.append(row)
    return out


def _score(q_tokens: list[str], note: sqlite3.Row, tags: list[str]) -> float:
    title_t = set(_tokens(note["title"] or ""))
    summary_t = set(_tokens(note["summary"] or ""))
    relpath_t = set(_tokens(note["relpath"] or ""))
    tag_t: set[str] = set()
    for t in tags:
        tag_t.update(_tokens(t))

    score = 0.0
    for q in q_tokens:
        if q in title_t:
            score += WEIGHTS["title"]
        if q in tag_t:
            score += WEIGHTS["tag"]
        if q in summary_t:
            score += WEIGHTS["summary"]
        if q in relpath_t:
            score += WEIGHTS["relpath"]
    return score
