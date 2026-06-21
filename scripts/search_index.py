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


def hydrate(db_path, *, vault_id: int, hits: list[dict],
            visibility: str | None = None) -> list[dict]:
    """Fill missing title/summary/tags on vector-sourced hits (which carry only
    relpath/score) from the notes table. fts hits already have a `title` key and are
    left untouched.

    When *visibility* is ``'public'`` the function also enforces the public boundary:
    vector-sourced hits whose note is NOT public are dropped, and hits whose relpath
    is not found in the notes table at all are also dropped (cannot verify visibility).
    When *visibility* is ``None`` no hits are dropped (backward-compatible).

    Best-effort — returns hits unmodified on any DB error (runs in the recall hot path).
    """
    need = [h["relpath"] for h in hits if h.get("relpath") and "title" not in h]
    if not need:
        return hits
    try:
        conn = registry.connect(db_path)
        try:
            ph = ",".join("?" for _ in need)
            meta = {r["relpath"]: r for r in conn.execute(
                f"SELECT relpath, title, summary, visibility FROM notes "
                f"WHERE vault_id = ? AND relpath IN ({ph})", (vault_id, *need))}
            tags: dict[str, list[str]] = {}
            for tr in conn.execute(
                f"SELECT n.relpath AS relpath, t.name AS name FROM notes n "
                f"JOIN note_tags nt ON nt.note_id = n.id "
                f"JOIN tags t ON t.id = nt.tag_id "
                f"WHERE n.vault_id = ? AND n.relpath IN ({ph})", (vault_id, *need)):
                tags.setdefault(tr["relpath"], []).append(tr["name"])
        finally:
            conn.close()
    except Exception:
        if visibility == "public":
            # fail closed: cannot verify visibility → keep only upstream-filtered fts hits
            # (those carry a `title`); drop every vector-sourced/untitled hit.
            return [h for h in hits if "title" in h]
        return hits   # visibility is None (recall hot path) → best-effort, no boundary
    out: list[dict] = []
    for h in hits:
        rel = h.get("relpath")
        if "title" in h:
            # fts-sourced hit: already visibility-filtered upstream — keep as-is.
            out.append(h)
            continue
        # vector-sourced hit (no title key).
        if rel not in meta:
            # Unknown / deleted relpath — can't verify visibility.
            if visibility == "public":
                continue  # drop: cannot confirm it's public
            out.append(h)
            continue
        note_vis = meta[rel]["visibility"]
        if visibility == "public" and note_vis != "public":
            continue  # drop: private note leaking through the public boundary
        h["title"] = meta[rel]["title"]
        h["summary"] = meta[rel]["summary"]
        h["tags"] = tags.get(rel, [])
        out.append(h)
    return out


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
        return hydrate(db_path, vault_id=vault_id, hits=emb_hits or fts_hits,
                       visibility=visibility)
    fused = rrf_fuse([[h["relpath"] for h in fts_hits],
                      [h["relpath"] for h in emb_hits]])
    meta = {h["relpath"]: h for h in (fts_hits + emb_hits)}
    out = []
    for relpath, score in fused[:limit]:
        row = dict(meta.get(relpath, {"relpath": relpath}))
        row["score"] = round(score, 4)
        out.append(row)
    return hydrate(db_path, vault_id=vault_id, hits=out, visibility=visibility)


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
