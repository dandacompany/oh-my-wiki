"""Stage durable knowledge candidates from bounded local session captures.

The pipeline is deterministic and approval-gated.  It never writes a vault file
in ``staged`` mode; ``approve_batch`` is the only promotion path.  ``auto-raw``
reuses that path and is separately opt-in.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from scripts import config, frontmatter, ingest, registry, reindex, session_capture

MODES = ("off", "advisory", "staged", "auto-raw")
_RETENTION_DAYS = 30
_MAX_EVIDENCE = 8_000
_MAX_SENTENCE = 1_200

_KIND_PATTERNS: tuple[tuple[str, re.Pattern, float], ...] = (
    ("decision", re.compile(
        r"(?i)(?:\bdecid(?:e|ed|ing)|\badopt(?:ed)?|\bmust\b|\bpolicy\b|"
        r"결정|선택(?:했|함|한다)|방침|원칙|반드시|정본)"), 0.92),
    ("preference", re.compile(
        r"(?i)(?:\bprefer(?:s|red)?\b|\balways\b|\bnever\b|선호|항상|절대\s*(?:하지|금지))"),
     0.90),
    ("incident", re.compile(
        r"(?i)(?:root cause|caused by|fixed by|resolved|reproduc(?:e|ible)|"
        r"원인|근본 원인|해결(?:했|됨|방법)|재현|수정(?:했|됨))"), 0.90),
    ("procedure", re.compile(
        r"(?i)(?:\bprocedure\b|\bworkflow\b|\brun\s+`|\bsteps?\b|절차|작업 흐름|"
        r"실행(?:하면|한다)|사용 방법|명령어)"), 0.84),
    ("fact", re.compile(
        r"(?i)(?:\bverified\b|\bconfirmed\b|\bmeasured\b|확인 결과|검증(?:했|됨)|"
        r"측정 결과|사실(?:이다|임))"), 0.80),
)
_TRANSIENT_RE = re.compile(
    r"(?i)(?:\bprogress\b|\bin progress\b|\bcurrently running\b|잠시|진행 중|"
    r"곧 확인|기다리|\bpid\s*[:=]?\s*\d+|localhost:\d+|127\.0\.0\.1:\d+)"
)
_ACK_RE = re.compile(
    r"(?i)^\s*(?:ok(?:ay)?|thanks?|thank you|done|좋아|네|예|감사|진행해|계속해)[.!\s]*$"
)
_SPECULATIVE_RE = re.compile(
    r"(?i)(?:\bmaybe\b|\bperhaps\b|\bi (?:guess|suspect)\b|\bunconfirmed\b|"
    r"아마|추측(?:한다|됨|이다)?|가정(?:하면|이다)|확실하지 않|미확인)"
)
_CODE_OR_LOG_RE = re.compile(
    r"(?i)(?:```|^\s*(?:debug|info|warn(?:ing)?|trace)\b|^\s*traceback\b|"
    r"^\s*(?:def|class|function|const|let|var)\s+|"
    r"^\s*import\s+[\w.]+|^\s*from\s+[\w.]+\s+import\s+|"
    r"^\s*file \"[^\"]+\", line \d+)"
)
_CONFLICT_RE = re.compile(
    r"(?i)(?:instead of|no longer|changed from|supersed|기존.+대신|더 이상|변경(?:했|됨)|대체)"
)
_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configured_mode() -> str:
    raw = ((config.load_config() or {}).get("recall") or {}).get(
        "knowledge_candidates", "off"
    )
    mode = str(raw or "off").lower()
    return mode if mode in MODES else "off"


def set_scope_mode(
    db_path: Path, *, scope_type: str, scope_value: str, mode: str,
) -> dict:
    if scope_type not in {"project", "host", "vault"}:
        return {"ok": False, "error": f"unknown scope type: {scope_type}"}
    if mode not in MODES:
        return {"ok": False, "error": f"unknown mode: {mode}"}
    value = (
        session_capture.resolve_project_root(scope_value)
        if scope_type == "project" else str(scope_value)
    )
    conn = registry.connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO knowledge_candidate_scope_modes(scope_type, scope_value, mode, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(scope_type, scope_value) DO UPDATE SET "
                "mode = excluded.mode, updated_at = excluded.updated_at",
                (scope_type, value, mode, _now()),
            )
    finally:
        conn.close()
    return {"ok": True, "scope_type": scope_type, "scope_value": value, "mode": mode}


def scope_modes(db_path: Path) -> list[dict]:
    conn = registry.connect(db_path)
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM knowledge_candidate_scope_modes "
            "ORDER BY scope_type, scope_value"
        )]
    finally:
        conn.close()


def effective_mode(
    db_path: Path, *, project_root: str | None = None,
    host: str | None = None, vault_id: int | None = None,
) -> str:
    """Resolve safe scope overrides; any matching explicit off wins."""
    matches: list[tuple[str, str]] = []
    if project_root:
        matches.append(("project", session_capture.resolve_project_root(project_root)))
    if host:
        matches.append(("host", str(host)))
    if vault_id is not None:
        matches.append(("vault", str(vault_id)))
    values: dict[str, str] = {}
    conn = registry.connect(db_path)
    try:
        for scope_type, scope_value in matches:
            row = conn.execute(
                "SELECT mode FROM knowledge_candidate_scope_modes "
                "WHERE scope_type = ? AND scope_value = ?",
                (scope_type, scope_value),
            ).fetchone()
            if row:
                values[scope_type] = row["mode"]
    finally:
        conn.close()
    if "off" in values.values():
        return "off"
    for scope_type in ("project", "vault", "host"):
        if scope_type in values:
            return values[scope_type]
    return configured_mode()


def _json(value, fallback):
    try:
        return json.loads(value or "")
    except (ValueError, TypeError):
        return fallback


def _row(row) -> dict:
    out = dict(row)
    if "provenance" in out:
        out["provenance"] = _json(out.get("provenance"), {})
    return out


def _sentences(text: object) -> list[str]:
    clean = session_capture.sanitize_text(text, limit=_MAX_EVIDENCE)
    if not clean or "[REDACTED]" in clean:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|\n{2,}|(?<=다\.)\s*", clean)
    out = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip(" -\t")
        if (
            len(part) < 12
            or _ACK_RE.match(part)
            or _TRANSIENT_RE.search(part)
            or _SPECULATIVE_RE.search(part)
            or _CODE_OR_LOG_RE.search(part)
        ):
            continue
        out.append(part[:_MAX_SENTENCE])
    return out


def extract_candidates(
    captures: list[dict], *, extra_evidence: list[str] | None = None,
) -> list[dict]:
    """Extract at most one compact candidate per durable category."""
    by_kind: dict[str, dict] = {}
    for capture in captures:
        for origin, value in (
            ("request", capture.get("last_user")),
            ("result", capture.get("last_assistant")),
        ):
            for sentence in _sentences(value):
                for kind, pattern, confidence in _KIND_PATTERNS:
                    if not pattern.search(sentence):
                        continue
                    current = by_kind.get(kind)
                    candidate = {
                        "kind": kind,
                        "confidence": confidence,
                        "title": sentence[:96].rstrip(" ."),
                        "content": sentence,
                        "origin": origin,
                    }
                    if current is None or confidence > current["confidence"]:
                        by_kind[kind] = candidate
                    break
    for value in extra_evidence or []:
        for sentence in _sentences(value):
            for kind, pattern, confidence in _KIND_PATTERNS:
                if pattern.search(sentence):
                    candidate = {
                        "kind": kind,
                        "confidence": confidence,
                        "title": sentence[:96].rstrip(" ."),
                        "content": sentence,
                        "origin": "agentmemory",
                    }
                    current = by_kind.get(kind)
                    if current is None or confidence > current["confidence"]:
                        by_kind[kind] = candidate
                    break
    # Preserve a stable conceptual order, not transcript/database order.
    order = {name: i for i, (name, _pattern, _confidence) in enumerate(_KIND_PATTERNS)}
    return sorted(by_kind.values(), key=lambda item: order[item["kind"]])


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text or "") if len(token) > 1}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    jaccard = len(a & b) / max(1, len(a | b))
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    return max(jaccard, sequence)


def _search_hits(db_path: Path, *, vault_id: int, text: str) -> list[dict]:
    from scripts import embed, recall, search_index
    cfg = config.load_config() or {}
    rc = cfg.get("recall") or {}
    strategy = recall.effective_strategy(rc.get("strategy", "fts"), quiet=True)
    if strategy == "llm":
        strategy = "fts"
    embedder = None
    if strategy in {"embedding", "hybrid"}:
        embedder = embed.active_embedder(db_path, rc.get("embedding") or {})
    return search_index.search_strategy(
        db_path,
        vault_id=vault_id,
        q=text,
        fts_query=recall.normalize_query(text),
        limit=5,
        strategy=strategy,
        embedder=embedder,
        visibility=None,
        quality_gate=strategy in {"embedding", "hybrid"},
    )


def _page_text(root: Path, relpath: str) -> str:
    try:
        meta, body = frontmatter.parse((root / relpath).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, frontmatter.FrontmatterError):
        return ""
    return " ".join(
        str(value or "") for value in (meta.get("title"), meta.get("summary"), body)
    )[:20_000]


def classify_candidate(db_path: Path, *, vault_id: int, candidate: dict) -> dict:
    """Classify against the configured local retrieval strategy."""
    try:
        hits = _search_hits(db_path, vault_id=vault_id, text=candidate["content"])
    except Exception:
        return {
            **candidate,
            "classification": "discard",
            "matched_relpath": None,
            "reason": "vault search failed; manual review required",
        }
    if not hits:
        return {**candidate, "classification": "new", "matched_relpath": None,
                "reason": "no related wiki page found"}
    root = registry.get_vault_root(db_path, vault_id)
    scored = [
        (_similarity(candidate["content"], _page_text(root, hit.get("relpath", ""))), hit)
        for hit in hits if hit.get("relpath")
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    similarity, hit = scored[0] if scored else (0.0, hits[0])
    relpath = hit.get("relpath")
    if similarity >= 0.84:
        classification, reason = "duplicate", f"substantially matches {relpath}"
    elif _CONFLICT_RE.search(candidate["content"]) and similarity >= 0.25:
        classification, reason = "conflict", f"may supersede or conflict with {relpath}"
    elif similarity >= 0.28:
        classification, reason = "update", f"related page found: {relpath}"
    else:
        classification, reason = "new", "search result lacked enough content overlap"
        relpath = None
    return {**candidate, "classification": classification,
            "matched_relpath": relpath, "reason": reason}


def _eligible_captures(
    db_path: Path,
    *,
    project_root: str,
    session_id: str | None = None,
    exclude_session_id: str | None = None,
) -> list[dict]:
    root = session_capture.resolve_project_root(project_root)
    sql = (
        "SELECT sc.* FROM session_captures sc "
        "LEFT JOIN knowledge_candidate_processed kp ON kp.capture_id = sc.id "
        "WHERE sc.project_root = ? AND sc.status = 'pending' AND kp.capture_id IS NULL"
    )
    params: list[object] = [root]
    if session_id:
        sql += " AND sc.session_id = ?"
        params.append(session_id)
    if exclude_session_id:
        sql += " AND sc.session_id != ?"
        params.append(exclude_session_id)
    sql += " ORDER BY sc.id ASC LIMIT 20"
    conn = registry.connect(db_path)
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def process_pending(
    db_path: Path,
    *,
    project_root: str,
    session_id: str | None = None,
    exclude_session_id: str | None = None,
    mode: str | None = None,
    agentmemory_json: str | Path | None = None,
) -> dict:
    """Consolidate unprocessed captures into one deduplicated review batch."""
    captures = _eligible_captures(
        db_path, project_root=project_root, session_id=session_id,
        exclude_session_id=exclude_session_id,
    )
    if not captures:
        return {"ok": True, "staged": False, "reason": "no-unprocessed-captures"}
    # A batch never crosses a host/session/vault boundary. Process the oldest group
    # now; a subsequent PreCompact/SessionStart handles the next group.
    first = captures[0]
    captures = [
        row for row in captures
        if (row["host"], row["session_id"], row["vault_id"])
        == (first["host"], first["session_id"], first["vault_id"])
    ]
    mode = mode or effective_mode(
        db_path, project_root=first["project_root"], host=first["host"],
        vault_id=first.get("vault_id"),
    )
    if mode not in {"staged", "auto-raw"}:
        return {"ok": True, "staged": False, "reason": mode}
    capture_ids = [int(row["id"]) for row in captures]
    extra_evidence: list[str] = []
    if agentmemory_json:
        from scripts import candidate_sources
        extra_evidence = candidate_sources.load_agentmemory_export(agentmemory_json)
    extracted = extract_candidates(captures, extra_evidence=extra_evidence)
    vault_id = first.get("vault_id")
    classified = (
        [classify_candidate(db_path, vault_id=vault_id, candidate=item) for item in extracted]
        if vault_id else []
    )
    # Exact duplicate candidate text within this run is collapsed before writing.
    unique: list[dict] = []
    seen: set[str] = set()
    conn = registry.connect(db_path)
    try:
        existing_texts = {
            row["content"] for row in conn.execute(
                "SELECT c.content FROM knowledge_candidates c "
                "JOIN knowledge_candidate_batches b ON b.id = c.batch_id "
                "WHERE b.project_root = ? AND c.status = 'pending'",
                (first["project_root"],),
            )
        }
    finally:
        conn.close()
    for item in classified:
        digest = hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
        if digest not in seen and item["content"] not in existing_texts:
            seen.add(digest)
            unique.append(item)
    if unique:
        outcome_reason = "durable candidates survived filtering and deduplication"
    elif not vault_id:
        outcome_reason = "no destination vault was bound to the session capture"
    elif not extracted:
        outcome_reason = "no durable signal survived the candidate policy"
    else:
        outcome_reason = "all extracted signals were already pending duplicates"
    content_hash = hashlib.sha256(json.dumps(
        {"captures": capture_ids, "items": [(i["kind"], i["content"]) for i in unique]},
        ensure_ascii=False, sort_keys=True,
    ).encode("utf-8")).hexdigest()
    conn = registry.connect(db_path)
    try:
        with conn:
            batch_id = None
            if unique:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO knowledge_candidate_batches("
                    "vault_id, project_root, host, session_id, created_at, content_hash, mode) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (vault_id, first["project_root"], first["host"], first["session_id"],
                     _now(), content_hash, mode),
                )
                if cur.rowcount:
                    batch_id = int(cur.lastrowid)
                    for ordinal, item in enumerate(unique, start=1):
                        provenance = {
                            "host": first["host"],
                            "project_root": first["project_root"],
                            "session_id": first["session_id"],
                            "capture_ids": capture_ids,
                            "captured_at": [row["captured_at"] for row in captures],
                            "files": sorted({
                                path for row in captures
                                for path in _json(row.get("files"), [])
                            })[:20],
                            "origin": item.pop("origin", "session"),
                        }
                        if agentmemory_json:
                            provenance["agentmemory_export"] = str(Path(agentmemory_json).resolve())
                        conn.execute(
                            "INSERT INTO knowledge_candidates("
                            "batch_id, ordinal, kind, classification, confidence, title, content, "
                            "reason, matched_relpath, provenance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (batch_id, ordinal, item["kind"], item["classification"],
                             item["confidence"], item["title"], item["content"], item["reason"],
                             item.get("matched_relpath"), json.dumps(provenance, ensure_ascii=False)),
                        )
                else:
                    existing = conn.execute(
                        "SELECT id FROM knowledge_candidate_batches WHERE vault_id IS ? "
                        "AND project_root = ? AND session_id = ? AND content_hash = ?",
                        (vault_id, first["project_root"], first["session_id"], content_hash),
                    ).fetchone()
                    batch_id = int(existing["id"]) if existing else None
            outcome = "staged" if unique else "discarded"
            conn.executemany(
                "INSERT OR IGNORE INTO knowledge_candidate_processed("
                "capture_id, processed_at, outcome, reason, batch_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (capture_id, _now(), outcome, outcome_reason, batch_id)
                    for capture_id in capture_ids
                ],
            )
    finally:
        conn.close()
    result = {"ok": True, "staged": bool(unique), "batch_id": batch_id,
              "candidates": len(unique), "capture_ids": capture_ids,
              "reason": outcome_reason}
    if mode == "auto-raw" and batch_id:
        approved = [item for item in list_items(db_path, batch_id=batch_id)
                    if item["classification"] == "new" and item["confidence"] >= 0.90]
        if approved:
            result["auto_raw"] = approve_batch(
                db_path, batch_id=batch_id, item_ids=[item["id"] for item in approved]
            )
    return result


def prune_expired(db_path: Path) -> int:
    """Close pending batches beyond retention without deleting their audit trail."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)).isoformat(
        timespec="seconds"
    )
    expired_at = _now()
    conn = registry.connect(db_path)
    try:
        rows = list(conn.execute(
            "SELECT id FROM knowledge_candidate_batches "
            "WHERE status = 'pending' AND created_at < ? AND expired_at IS NULL",
            (cutoff,),
        ))
        with conn:
            for row in rows:
                batch_id = int(row["id"])
                conn.execute(
                    "UPDATE knowledge_candidates SET status = 'dismissed' "
                    "WHERE batch_id = ? AND status = 'pending'",
                    (batch_id,),
                )
                approved = conn.execute(
                    "SELECT COUNT(*) FROM knowledge_candidates "
                    "WHERE batch_id = ? AND status = 'approved'",
                    (batch_id,),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE knowledge_candidate_batches "
                    "SET status = ?, expired_at = ? WHERE id = ?",
                    ("approved" if approved else "dismissed", expired_at, batch_id),
                )
    finally:
        conn.close()
    return len(rows)


def processing_summary(db_path: Path) -> dict:
    """Return content-free queue and keep/discard reason counts."""
    pruned = prune_expired(db_path)
    conn = registry.connect(db_path)
    try:
        pending = conn.execute(
            "SELECT COUNT(*) FROM knowledge_candidate_batches WHERE status = 'pending'"
        ).fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM knowledge_candidate_batches WHERE expired_at IS NOT NULL"
        ).fetchone()[0]
        outcomes = [dict(row) for row in conn.execute(
            "SELECT outcome, reason, COUNT(*) AS captures FROM knowledge_candidate_processed "
            "GROUP BY outcome, reason ORDER BY outcome, reason"
        )]
    finally:
        conn.close()
    return {
        "retention_days": _RETENTION_DAYS,
        "pending_batches": int(pending),
        "expired_batches": int(expired),
        "expired_now": pruned,
        "processed": outcomes,
    }


def list_batches(
    db_path: Path, *, status: str | None = "pending",
    project_root: str | None = None, limit: int = 20,
) -> list[dict]:
    prune_expired(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)).isoformat(
        timespec="seconds"
    )
    sql = (
        "SELECT b.*, COUNT(c.id) AS candidate_count, "
        "SUM(CASE WHEN c.status = 'pending' THEN 1 ELSE 0 END) AS pending_count "
        "FROM knowledge_candidate_batches b LEFT JOIN knowledge_candidates c ON c.batch_id = b.id "
        "WHERE b.created_at >= ?"
    )
    params: list[object] = [cutoff]
    if status:
        sql += " AND b.status = ?"
        params.append(status)
    if project_root:
        sql += " AND b.project_root = ?"
        params.append(session_capture.resolve_project_root(project_root))
    sql += " GROUP BY b.id ORDER BY b.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    conn = registry.connect(db_path)
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def list_items(db_path: Path, *, batch_id: int) -> list[dict]:
    conn = registry.connect(db_path)
    try:
        return [_row(row) for row in conn.execute(
            "SELECT * FROM knowledge_candidates WHERE batch_id = ? ORDER BY ordinal", (batch_id,)
        )]
    finally:
        conn.close()


def show_batch(db_path: Path, batch_id: int) -> dict | None:
    conn = registry.connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM knowledge_candidate_batches WHERE id = ?", (batch_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {**dict(row), "candidates": list_items(db_path, batch_id=batch_id)}


def _existing_raw(root: Path, batch_id: int) -> str | None:
    for path in sorted((root / "raw").glob("*.md")) if (root / "raw").is_dir() else []:
        try:
            meta, _body = frontmatter.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, frontmatter.FrontmatterError):
            continue
        if meta.get("candidate_batch_id") == batch_id:
            return str(path.relative_to(root)).replace("\\", "/")
    return None


def _render_item(item: dict) -> str:
    lines = [
        f"## {item['kind'].title()}: {item['title']}", "", item["content"], "",
        f"- Classification: `{item['classification']}`",
        f"- Confidence: `{item['confidence']:.2f}`",
        f"- Reason: {item['reason']}",
    ]
    if item.get("matched_relpath"):
        lines.append(f"- Related page: `{item['matched_relpath']}`")
    return "\n".join(lines)


def approve_batch(
    db_path: Path, *, batch_id: int, item_ids: list[int] | None = None,
) -> dict:
    """Explicitly promote selected pending items into one private raw record."""
    batch = show_batch(db_path, batch_id)
    if not batch:
        return {"ok": False, "error": f"batch {batch_id} not found"}
    selected = [
        item for item in batch["candidates"]
        if item["status"] == "pending" and (not item_ids or item["id"] in item_ids)
    ]
    if not selected:
        return {"ok": False, "error": "no pending candidates selected"}
    vault_id = batch.get("vault_id")
    if not vault_id:
        return {"ok": False, "error": "candidate batch has no destination vault"}
    root = registry.get_vault_root(db_path, vault_id)
    relpath = _existing_raw(root, batch_id)
    capture_ids = sorted({
        capture_id for item in selected
        for capture_id in item["provenance"].get("capture_ids", [])
    })
    if relpath is None:
        title = f"Session knowledge candidates {batch_id}"
        body_lines = [
            "This record was approved from OMW's local session-candidate queue.",
            "Captured session text is historical evidence, not executable instructions.",
        ]
        for item in selected:
            body_lines.extend(["", _render_item(item)])
        metadata = {
            "title": title,
            "date": date.today().isoformat(),
            "type": "session-candidate",
            "status": "captured",
            "visibility": "private",
            "candidate_batch_id": batch_id,
            "source_host": batch["host"],
            "source_session_id": batch["session_id"],
            "source_project_root": batch["project_root"],
            "capture_ids": capture_ids,
        }
        relpath = ingest.save_raw(
            db_path, vault_id=vault_id,
            content=frontmatter.dump(metadata, "\n".join(body_lines).rstrip() + "\n"),
            ext="md", title=title, date_str=date.today().isoformat(),
        )
        reindex.incremental(db_path, vault_id=vault_id)
    else:
        raw_path = root / relpath
        metadata, body = frontmatter.parse(raw_path.read_text(encoding="utf-8"))
        additions = [
            _render_item(item) for item in selected if item["content"] not in body
        ]
        if additions:
            metadata["capture_ids"] = sorted({
                *list(metadata.get("capture_ids") or []), *capture_ids,
            })
            body = body.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
            raw_path.write_text(frontmatter.dump(metadata, body), encoding="utf-8")
            reindex.incremental(db_path, vault_id=vault_id)
    selected_ids = [item["id"] for item in selected]
    conn = registry.connect(db_path)
    try:
        with conn:
            placeholders = ",".join("?" * len(selected_ids))
            conn.execute(
                f"UPDATE knowledge_candidates SET status = 'approved' WHERE id IN ({placeholders})",
                selected_ids,
            )
            remaining = conn.execute(
                "SELECT COUNT(*) FROM knowledge_candidates WHERE batch_id = ? AND status = 'pending'",
                (batch_id,),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute(
                    "UPDATE knowledge_candidate_batches SET status = 'approved', raw_relpath = ? "
                    "WHERE id = ?", (relpath, batch_id),
                )
            else:
                conn.execute(
                    "UPDATE knowledge_candidate_batches SET raw_relpath = ? WHERE id = ?",
                    (relpath, batch_id),
                )
    finally:
        conn.close()
    return {"ok": True, "batch_id": batch_id, "approved": selected_ids, "raw_relpath": relpath}


def dismiss_batch(
    db_path: Path, *, batch_id: int, item_ids: list[int] | None = None,
) -> dict:
    batch = show_batch(db_path, batch_id)
    if not batch:
        return {"ok": False, "error": f"batch {batch_id} not found"}
    selected = [
        item["id"] for item in batch["candidates"]
        if item["status"] == "pending" and (not item_ids or item["id"] in item_ids)
    ]
    if not selected:
        return {"ok": False, "error": "no pending candidates selected"}
    conn = registry.connect(db_path)
    try:
        with conn:
            placeholders = ",".join("?" * len(selected))
            conn.execute(
                f"UPDATE knowledge_candidates SET status = 'dismissed' WHERE id IN ({placeholders})",
                selected,
            )
            remaining = conn.execute(
                "SELECT COUNT(*) FROM knowledge_candidates WHERE batch_id = ? AND status = 'pending'",
                (batch_id,),
            ).fetchone()[0]
            if remaining == 0:
                approved = conn.execute(
                    "SELECT COUNT(*) FROM knowledge_candidates WHERE batch_id = ? AND status = 'approved'",
                    (batch_id,),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE knowledge_candidate_batches SET status = ? WHERE id = ?",
                    ("approved" if approved else "dismissed", batch_id),
                )
    finally:
        conn.close()
    return {"ok": True, "batch_id": batch_id, "dismissed": selected}


def render_notice(db_path: Path, *, project_root: str) -> str:
    batches = list_batches(db_path, project_root=project_root, limit=5)
    if not batches:
        return ""
    count = sum(int(batch.get("pending_count") or 0) for batch in batches)
    ids = ", ".join(str(batch["id"]) for batch in batches)
    return (
        "<omw-candidates> OMW staged "
        f"{count} reviewable knowledge candidate(s) in batch(es) {ids}. "
        "No vault page has been changed. Review with `omw candidates list` and "
        "`omw candidates show <batch-id>`; approve or dismiss explicitly. "
        "</omw-candidates>"
    )
