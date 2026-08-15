"""Weighted natural-language search over the sqlite notes index."""
from __future__ import annotations

import re
import sqlite3
import json
import os
import sys
from difflib import SequenceMatcher
from pathlib import Path

from scripts import fts, registry

WEIGHTS = {
    "title": 5.0,
    "tag": 3.0,
    "summary": 1.5,
    "relpath": 1.0,
}

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)

# Instruction words are useful to the agent, but weak evidence that a wiki page is
# about the user's subject.  Keeping them out of the recall quality score prevents
# pages from matching only on words such as "compare", "test", or "explain".
_QUERY_STOPWORDS = {
    "관련", "대해", "대한", "현재", "문제", "방법", "설명", "알려줘", "해줘",
    "작성", "확인", "그리고", "먼저", "나중", "반드시", "다양", "다양하게",
    "설정", "진행", "구현", "테스트", "검색", "품질", "비교", "봐", "해봐",
    "the", "a", "an", "and", "or", "about", "how", "what", "please",
    "show", "explain", "write", "compare", "test", "search", "issue", "problem",
}


def _tokens(text: str) -> list[str]:
    from scripts import text_normalize
    normalized = text_normalize.normalize_text(text or "")
    return [t.lower() for t in _TOKEN_RE.findall(normalized)]


def _key_tokens(text: str) -> list[str]:
    """Tokens carrying subject matter rather than prompt instructions."""
    return [t for t in _tokens(text) if t not in _QUERY_STOPWORDS and len(t) > 1]


_ASCII_TOKEN_RE = re.compile(r"^[a-z0-9_.-]+$", re.IGNORECASE)


def _technical_token_match(left: str, right: str) -> bool:
    """Tolerate small ASCII identifier typos and common numeric abbreviations."""
    if left == right:
        return True
    if not (_ASCII_TOKEN_RE.match(left) and _ASCII_TOKEN_RE.match(right)):
        return False
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 2 and any(ch.isdigit() for ch in shorter) and longer.startswith(shorter):
        return True
    return len(shorter) >= 4 and SequenceMatcher(None, left, right).ratio() >= 0.84


def query(
    db_path: Path,
    *,
    vault_id: int,
    query: str,
    limit: int = 5,
    visibility: str | None = None,
    include_match_text: bool = False,
) -> list[dict]:
    """Return top-N hits as dicts {relpath, title, summary, tags, score}.
    When visibility='public', only public pages are returned (used by `omw serve`)."""
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    if fts.fts5_available():
        fts_kwargs = {
            "vault_id": vault_id, "query": query, "limit": limit,
            "visibility": visibility,
        }
        if include_match_text:
            fts_kwargs["include_match_text"] = True
        hits = fts.search(db_path, **fts_kwargs)
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


def _candidate_aliases(db_path, *, vault_id: int, relpaths: list[str]) -> dict[str, list[str]]:
    """Load aliases for recall scoring without exposing them in public hit objects."""
    if not relpaths or db_path is None:
        return {}
    try:
        conn = registry.connect(db_path)
        try:
            ph = ",".join("?" for _ in relpaths)
            rows = conn.execute(
                f"SELECT relpath, aliases FROM notes WHERE vault_id = ? "
                f"AND relpath IN ({ph})", (vault_id, *relpaths),
            )
            out: dict[str, list[str]] = {}
            for row in rows:
                try:
                    value = json.loads(row["aliases"] or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    value = []
                out[row["relpath"]] = [str(v) for v in value] if isinstance(value, list) else []
            return out
        finally:
            conn.close()
    except Exception:
        return {}


def _candidate_body_texts(db_path, *, vault_id: int,
                          relpaths: list[str], max_chars: int = 20_000) -> dict[str, str]:
    """Load bounded body text only for the strongest FTS candidates.

    FTS snippets show one local window and can miss query terms that occur in
    distant sections.  Reading at most three bounded bodies gives the quality
    gate enough evidence without loading every candidate document on each hook.
    """
    relpaths = [rel for rel in relpaths if rel]
    if not relpaths or db_path is None:
        return {}
    try:
        conn = registry.connect(db_path)
        try:
            ph = ",".join("?" for _ in relpaths)
            rows = conn.execute(
                f"SELECT relpath, substr(body, 1, ?) AS body FROM notes_fts "
                f"WHERE vault_id = ? AND relpath IN ({ph})",
                (max_chars, str(vault_id), *relpaths),
            )
            return {row["relpath"]: row["body"] or "" for row in rows}
        finally:
            conn.close()
    except Exception:
        return {}


def _coverage(query_tokens: set[str], text: str) -> tuple[float, int, set[str]]:
    field = set(_key_tokens(text))
    matched_query: set[str] = set()
    matched_field: set[str] = set()
    for query_token in query_tokens:
        for field_token in field:
            if _technical_token_match(query_token, field_token):
                matched_query.add(query_token)
                matched_field.add(field_token)
                break
    return (
        len(matched_field) / len(field) if field else 0.0,
        len(matched_query),
        matched_query,
    )


#: shortest word specific enough to name a page. Latin words match on word
#: boundaries, so 'db' would still catch dbt/mariadb/sandbox — hold those to 3.
#: Hangul has no boundaries to match on, but 2 syllables is already a word.
_MIN_NAME_WORD_LATIN = 3
_MIN_NAME_WORD_HANGUL = 2


def _fold(text: str) -> str:
    """Case- and unicode-normalized form for name comparison (NFD vaults on SMB)."""
    import unicodedata
    return unicodedata.normalize("NFC", text).casefold()


def _name_words(term: str) -> list[str]:
    """Words of a search term, or [] when it is too weak to name a page.

    Separators are not meaningful — the analyzer splits `key-rotation` into
    `key` and `rotation`, so a page titled "Key rotation" must still match.
    Purely numeric words (dates, versions) are dropped: they name a file naming
    convention rather than any subject.
    """
    words = []
    for word in re.split(r"[-_.\s]+", _fold(term)):
        if not word or word.isdigit():
            return []
        if len(word) < (_MIN_NAME_WORD_LATIN if word.isascii() else _MIN_NAME_WORD_HANGUL):
            return []
        words.append(word)
    return words


def name_terms(query: str) -> list[list[str]]:
    """Query terms specific enough to judge a hit by name, each split into words.
    Empty when nothing in the query is specific enough — callers decide what
    that means for them (see `names_query`'s `on_vague`)."""
    return [words for term in (query or "").split() if (words := _name_words(term))]


def _word_present(word: str, haystack: str) -> bool:
    if not word.isascii():
        if word in haystack:
            return True
        # A prompt carries postpositions its target page does not: '번들을' must
        # still find "페르소나 번들".
        from scripts import text_normalize
        stripped = text_normalize.strip_josa(word)
        return stripped != word and len(stripped) >= _MIN_NAME_WORD_HANGUL \
            and stripped in haystack
    # a bare substring would let 'box' match 'sandbox'
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", haystack) is not None


def names_query(hits: list[dict], query: str, *,
                on_vague: str = "keep") -> list[dict]:
    """Keep only hits whose own title or relpath names a term of the query.

    A precision gate for callers that must not inject noise — the recall hooks
    fire on every prompt and every tool call. Scores cannot do this job:
    measured on a live vault, the apt query '페르소나 번들' peaked at 5.73 with
    entirely correct hits while 'packages db key-rotation' reached 11.49 with
    entirely wrong ones, because a common word matching often in a long
    document outscores a real topical match. A page that *names* a term is
    about it; body-only matches are dropped — which does mean a page that
    discusses a topic without naming it in its title or path cannot surface
    through this gate. That trade is deliberate for auto-injection.

    `on_vague` decides what happens when no query term is specific enough:
    "keep" falls back to the caller's own ranking, "drop" returns nothing (for
    callers whose whole query was noise, like a shell command with no paths).
    """
    terms = name_terms(query)
    if not terms:
        return [] if on_vague == "drop" else hits
    kept = []
    for hit in hits:
        haystack = _fold(f"{hit.get('relpath') or ''} {hit.get('title') or ''}")
        if any(all(_word_present(w, haystack) for w in words) for words in terms):
            kept.append(hit)
    return kept


def _relative_prune(ranked: list[tuple[float, dict]], *, limit: int,
                    ratio: float = 0.80) -> list[dict]:
    """Keep only candidates reasonably close to the best supported result."""
    if not ranked:
        return []
    floor = ranked[0][0] * ratio
    return [hit for score, hit in ranked if score >= floor][:limit]


def _quality_rank(db_path, *, vault_id: int, q: str, fts_hits: list[dict],
                  emb_hits: list[dict], limit: int, visibility=None) -> list[dict]:
    """Rank and gate hook-side recall candidates using observable evidence.

    RRF is deliberately not used as a confidence score here: with k=60 even an
    unrelated rank-1 result receives ~0.016, which made a 0.01 threshold accept
    nearly everything.  This path preserves each leg's raw score, rewards exact
    title/alias evidence and two-leg agreement, and returns no result when the
    evidence is weak.
    """
    candidates: dict[str, dict] = {}
    for rank, hit in enumerate(fts_hits, 1):
        rel = hit.get("relpath")
        if not rel:
            continue
        row = candidates.setdefault(rel, {"relpath": rel})
        for key in ("title", "summary", "tags", "_match_text"):
            if hit.get(key) is not None:
                row[key] = hit.get(key)
        row["_fts_rank"] = rank
        row["_fts_score"] = float(hit.get("score") or 0.0)
    for rank, hit in enumerate(emb_hits, 1):
        rel = hit.get("relpath")
        if not rel:
            continue
        row = candidates.setdefault(rel, {"relpath": rel})
        row["_vec_rank"] = rank
        row["_vec_score"] = float(hit.get("score") or 0.0)

    hydrated = hydrate(
        db_path, vault_id=vault_id,
        hits=[{k: v for k, v in row.items() if not k.startswith("_")} for row in candidates.values()],
        visibility=visibility,
    )
    allowed = {h.get("relpath") for h in hydrated}
    hydrated_by_rel = {h.get("relpath"): h for h in hydrated}
    aliases = _candidate_aliases(db_path, vault_id=vault_id, relpaths=list(allowed))
    top_fts_relpaths = [
        rel for rel, row in candidates.items()
        if 0 < int(row.get("_fts_rank") or 0) <= 3 and rel in allowed
    ]
    body_texts = _candidate_body_texts(
        db_path, vault_id=vault_id, relpaths=top_fts_relpaths,
    )
    query_tokens = set(_key_tokens(q))
    if not query_tokens:
        return []

    # A high semantic score is useful only when it is distinctive.  The margin
    # blocks generic queries whose nearest neighbours are all similarly mediocre.
    vec_scores = sorted(
        (row.get("_vec_score", 0.0) for rel, row in candidates.items() if rel in allowed),
        reverse=True,
    )
    second_vec = vec_scores[1] if len(vec_scores) > 1 else 0.0

    ranked: list[tuple[float, dict]] = []
    for rel, row in candidates.items():
        if rel not in allowed:
            continue
        public = dict(hydrated_by_rel.get(rel) or {"relpath": rel})
        title_cov, title_matches, title_terms = _coverage(query_tokens, public.get("title") or "")
        alias_cov = 0.0
        alias_matches = 0
        alias_terms: set[str] = set()
        for alias in aliases.get(rel, []):
            cov, count, terms = _coverage(query_tokens, alias)
            if cov > alias_cov:
                alias_cov, alias_matches, alias_terms = cov, count, terms
        tag_cov = 0.0
        tag_terms: set[str] = set()
        for tag in public.get("tags") or []:
            cov, _count, terms = _coverage(query_tokens, str(tag))
            tag_cov = max(tag_cov, cov)
            tag_terms.update(terms)
        tag_matches = len(tag_terms)
        summary_cov, summary_matches, summary_terms = _coverage(
            query_tokens, public.get("summary") or "",
        )
        _body_cov, _body_matches, body_terms = _coverage(
            query_tokens, body_texts.get(rel) or row.get("_match_text") or "",
        )
        matched_terms = title_terms | alias_terms | tag_terms | summary_terms | body_terms
        query_cov = len(matched_terms) / len(query_tokens)
        body_query_cov = len(body_terms) / len(query_tokens)
        name_cov = max(title_cov, alias_cov)
        name_matches = max(title_matches, alias_matches)
        name_signal = 0.72 * name_cov + 0.28 * query_cov
        # A one-token entity page can answer "what is X", but should not dominate
        # a multi-fact question merely because X appears in it.
        if name_matches == 1 and len(query_tokens) >= 3:
            name_signal = min(name_signal, 0.38)
        tag_signal = 0.50 * tag_cov + 0.30 * query_cov
        if tag_matches < 2 and query_cov < 0.40:
            tag_signal = min(tag_signal, 0.35)
        lexical = max(
            name_signal,
            tag_signal,
            0.28 * summary_cov + 0.12 * query_cov,
            0.46 * body_query_cov,
        )
        exact_name = name_matches >= 2 and name_cov >= 0.78

        vec = float(row.get("_vec_score") or 0.0)
        semantic = max(0.0, min(1.0, (vec - 0.60) / 0.20))
        fts_rank = int(row.get("_fts_rank") or 0)
        vec_rank = int(row.get("_vec_rank") or 0)
        agreement = bool(fts_rank and vec_rank)
        structured = rel.startswith("wiki/")
        quality = (
            0.52 * lexical
            + 0.25 * semantic
            + (0.10 if agreement else 0.0)
            + (0.05 / fts_rank if fts_rank else 0.0)
            + (0.04 / vec_rank if vec_rank else 0.0)
            + (0.04 if structured else 0.0)
        )
        if exact_name:
            quality = max(quality, 0.92)

        semantic_margin = vec - second_vec if vec == (vec_scores[0] if vec_scores else 0.0) else 0.0
        relevant = (
            exact_name
            or (fts_rank > 0 and lexical >= 0.48)
            or (0 < fts_rank <= 3 and body_query_cov >= 0.75)
            or (agreement and lexical >= 0.18 and semantic >= 0.35 and quality >= 0.34)
            or (vec >= 0.78 and semantic_margin >= 0.04 and quality >= 0.45)
        )
        if os.environ.get("OMW_RECALL_DEBUG") == "1":
            print(json.dumps({
                "relpath": rel,
                "fts_rank": fts_rank,
                "vector_rank": vec_rank,
                "vector_score": round(vec, 4),
                "lexical": round(lexical, 4),
                "body_query_coverage": round(body_query_cov, 4),
                "exact_name": exact_name,
                "quality": round(quality, 4),
                "relevant": relevant,
            }, ensure_ascii=False), file=sys.stderr)
        if not relevant:
            continue
        public["score"] = round(min(1.0, quality), 4)
        ranked.append((quality, public))

    ranked.sort(key=lambda item: (-item[0], 0 if item[1]["relpath"].startswith("wiki/") else 1,
                                  item[1]["relpath"]))
    return _relative_prune(ranked, limit=limit)


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
                    embedder=None, visibility=None, fts_query=None,
                    quality_gate: bool = False):
    """fts → existing query(); embedding → vector store; hybrid → RRF(fts, embedding).
    Falls back to fts when embedding unusable."""
    candidate_limit = (
        max(24, limit * 8)
        if quality_gate and strategy in {"hybrid", "embedding"}
        else limit
    )
    query_kwargs = {
        "vault_id": vault_id, "query": (fts_query or q), "limit": candidate_limit,
        "visibility": visibility,
    }
    if quality_gate:
        query_kwargs["include_match_text"] = True
    fts_hits = query(db_path, **query_kwargs)
    if strategy == "fts":
        return fts_hits
    if embedder is None:
        if quality_gate:
            return _quality_rank(db_path, vault_id=vault_id, q=q, fts_hits=fts_hits,
                                 emb_hits=[], limit=limit, visibility=visibility)
        return fts_hits
    from scripts import vector_index
    emb_hits = vector_index.query(db_path, vault_id=vault_id, embedder=embedder,
                                  text=q, limit=candidate_limit)
    if strategy == "embedding":
        if quality_gate:
            return _quality_rank(db_path, vault_id=vault_id, q=q, fts_hits=[],
                                 emb_hits=emb_hits, limit=limit, visibility=visibility)
        return hydrate(db_path, vault_id=vault_id, hits=emb_hits or fts_hits,
                       visibility=visibility)
    if quality_gate:
        return _quality_rank(db_path, vault_id=vault_id, q=q, fts_hits=fts_hits,
                             emb_hits=emb_hits, limit=limit, visibility=visibility)
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
