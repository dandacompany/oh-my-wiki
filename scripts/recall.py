"""omw recall — host-agnostic wiki recall for agent hooks.

See references/auto-recall-hook-design.md. Two entrypoints, both called by host
hooks; their stdout is injected into the agent as context:

  preamble : session-start summary (active vault + recent pages)        [Tier 0]
  prompt   : per-prompt FTS recall — inject top hits when relevant      [Tier 2]

Plus `render_recall_block()` which produces the host-instruction-file guidance
block (Tier 1) that `omw setup recall` writes into CLAUDE.md/AGENTS.md/GEMINI.md.

Contract: best-effort and non-blocking. Prints injectable text to stdout; empty
output means "no injection". Never raises to the host.
"""
from __future__ import annotations

import sys

from scripts import maint

MARKER = "omw-recall"
CAPTURE_MARKER = "omw-capture"

#: retrieval strategies (축 2). All of `fts`, `embedding`, `hybrid`, `llm` are
#: implemented; only an unknown/unconfigured strategy falls back to `fts`
#: (see references/auto-recall-hook-design.md §10). `llm` is agent-delegated guidance
#: (advisory-natured — the hook emits an instruction and makes no LLM/API call).
STRATEGIES = ("fts", "embedding", "hybrid", "llm")
LLM_SUBMODES = ("route", "generative")
_IMPLEMENTED_STRATEGIES = {"fts", "embedding", "hybrid", "llm"}

# min_score=1.0 keeps weak plain-FTS results out of automatic injection. FTS5
# searches metadata and body text; embedding/hybrid recall additionally applies
# the evidence-based quality gate in search_index before this final threshold.
_STRATEGY_MIN_SCORES = {"fts": 1.0, "embedding": 0.34, "hybrid": 0.34}
_DEFAULTS = {"mode": "auto", "strategy": "fts", "llm_submode": "route",
             "min_score": 1.0, "min_scores": dict(_STRATEGY_MIN_SCORES),
             "top_k": 3, "snippet_chars": 280,
             "capture": True, "session_capture": True,
             "knowledge_candidates": "off"}


def effective_strategy(strategy: str, *, quiet: bool = False) -> str:
    """Resolve the configured strategy to an implemented one. All named STRATEGIES
    (fts/embedding/hybrid/llm) are implemented; only an unrecognized strategy falls
    back to `fts`. `quiet=True` on the per-prompt hot path; the note is only useful
    on explicit `omw recall`/setup invocations."""
    if strategy in _IMPLEMENTED_STRATEGIES:
        return strategy
    if strategy in STRATEGIES and not quiet:  # reserved for a future not-yet-built strategy
        print(f"omw recall: strategy '{strategy}' is not yet implemented "
              f"— using 'fts'. (references/auto-recall-hook-design.md §10)", file=sys.stderr)
    return "fts"


def cost_warning(mode: str, strategy: str) -> str | None:
    """Note for auto+llm. Under the agent-delegated llm design the hook makes NO
    separate API call — it just emits guidance every prompt; advisory is the natural pairing."""
    if mode == "auto" and strategy == "llm":
        return ("Note: the llm strategy is advisory. Even in auto mode, the hook delegates "
                "retrieval to the in-loop agent instead of injecting results, and it makes "
                "no separate API call. Advisory mode is recommended.")
    return None

# Short acknowledgements / continuations that should never trigger recall.
_ACK = {
    "ok", "okay", "k", "y", "yes", "n", "no", "thanks", "thank you", "continue",
    "네", "응", "옙", "ㅇㅋ", "고마워", "계속", "그래", "맞아", "좋아",
}


def _as_bool(v) -> bool:
    """Normalize a hand-edited toggle. A bare non-empty string like 'off' is truthy in
    Python, so parse explicitly instead of trusting bool(v)."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("on", "true", "yes", "1")
    if isinstance(v, (int, float)):
        return bool(v)
    return False


def _cfg() -> dict:
    try:
        from scripts import config
        raw = (config.load_config() or {}).get("recall") or {}
    except Exception:
        raw = {}
    out = dict(_DEFAULTS)
    # Keep nested defaults isolated per load. A shallow copy alone would let a
    # configured threshold mutate _DEFAULTS for every later recall in-process.
    out["min_scores"] = dict(_DEFAULTS["min_scores"])
    for k in ("mode", "strategy", "min_score", "top_k", "snippet_chars"):
        if k in raw:
            out[k] = raw[k]
    configured_thresholds = raw.get("min_scores")
    if isinstance(configured_thresholds, dict):
        out["min_scores"].update({
            k: v for k, v in configured_thresholds.items()
            if k in _STRATEGY_MIN_SCORES
        })
    llm = raw.get("llm")  # harden: a hand-edited non-dict must not raise here
    out["llm_submode"] = (llm if isinstance(llm, dict) else {}).get("submode", _DEFAULTS["llm_submode"])
    out["capture"] = _as_bool(raw.get("capture", _DEFAULTS["capture"]))
    out["session_capture"] = _as_bool(
        raw.get("session_capture", _DEFAULTS["session_capture"]))
    candidate_mode = str(raw.get(
        "knowledge_candidates", _DEFAULTS["knowledge_candidates"]
    ) or "off").lower()
    out["knowledge_candidates"] = (
        candidate_mode
        if candidate_mode in {"off", "advisory", "staged", "auto-raw"}
        else "off"
    )
    return out


def score_threshold(cfg: dict, strategy: str) -> float:
    """Return a threshold in the score scale produced by one strategy.

    The legacy scalar ``min_score`` remains the FTS override. Embedding/hybrid
    scores are normalized 0..1 and use ``min_scores.<strategy>`` instead.
    """
    if strategy == "fts":
        return float(cfg.get("min_score", _STRATEGY_MIN_SCORES["fts"]))
    values = cfg.get("min_scores") if isinstance(cfg.get("min_scores"), dict) else {}
    return float(values.get(strategy, _STRATEGY_MIN_SCORES.get(strategy, 0.0)))


def threshold_diagnostics(cfg: dict) -> list[str]:
    """Explain threshold settings that can never accept a normalized score."""
    warnings = []
    for strategy in ("embedding", "hybrid"):
        threshold = score_threshold(cfg, strategy)
        if threshold > 1.0:
            warnings.append(
                f"recall.min_scores.{strategy}={threshold:g} is unreachable; "
                "normalized scores are at most 1.0"
            )
        elif threshold < 0:
            warnings.append(
                f"recall.min_scores.{strategy}={threshold:g} is below the 0..1 score range"
            )
    return warnings


def is_trivial(text: str) -> bool:
    """True for prompts not worth a wiki lookup (too short / pure ack)."""
    t = (text or "").strip()
    return len(t) < 12 or t.lower() in _ACK


def _active(db):
    from scripts import registry
    return registry.get_active(db)


def _has_active_vault() -> bool:
    """True if there's an active vault to capture into. Best-effort; never raises.
    Gates the (default-on) capture cue so a vault-less install isn't nudged to ingest
    into a wiki that doesn't exist yet."""
    try:
        from scripts.paths import registry_path
        db = registry_path()
        return db.exists() and bool(_active(db))
    except Exception:
        return False


def _strip_josa(token: str) -> str:
    """Drop a trailing Korean postposition (delegates to text_normalize)."""
    from scripts import text_normalize
    return text_normalize.normalize_token(token)


def normalize_query(text: str) -> str:
    """Josa-normalize a free-text prompt for FTS recall (delegates to
    text_normalize so the index and query use the same analyzer)."""
    from scripts import text_normalize
    return text_normalize.normalize_text(text)


def _record_use(relpaths: list[str]) -> None:
    """Stamp surfaced pages as used today in the active vault's usage store.
    Best-effort — recall runs on every prompt and must never raise to the host."""
    try:
        from datetime import date
        from scripts import registry, usage
        from scripts.paths import registry_path
        db = registry_path()
        v = registry.get_active(db)
        if v:
            usage.bump(v["path"], relpaths, date.today().isoformat())
    except Exception:
        pass


def _hits(text: str, top_k: int) -> list[dict]:
    try:
        from scripts import config
        from scripts.paths import registry_path
        cfg = config.load_config()
        rc = (cfg or {}).get("recall", {})
        # llm strategy is advisory-natured: the hook never runs a Python search;
        # it emits guidance and delegates retrieval to the in-loop agent entirely.
        # Guard here so no embedder/search_index/vector_index is ever touched.
        strat = effective_strategy(rc.get("strategy", "fts"), quiet=True)
        if strat == "llm":
            return []
        from scripts import search_index, embed
        db = registry_path()
        if not db.exists():
            return []
        v = _active(db)
        if not v:
            return []
        visibility = rc.get("visibility", None)

        if strat == "fts":
            return search_index.query(db, vault_id=v["id"],
                                      query=normalize_query(text),
                                      limit=top_k, visibility=visibility)
        else:
            embedder = embed.active_embedder(
                db, (cfg.get("recall") or {}).get("embedding") or {}
            )
            return search_index.search_strategy(db, vault_id=v["id"],
                                                q=text, fts_query=normalize_query(text),
                                                limit=top_k,
                                                strategy=strat,
                                                embedder=embedder,
                                                visibility=visibility,
                                                quality_gate=(strat in ("hybrid", "embedding")))
    except Exception:
        return []


#: stdin JSON keys host UserPromptSubmit hooks use to carry the user's prompt.
_PROMPT_KEYS = ("prompt", "user_prompt", "current_prompt", "message", "text", "input")


def _prompt_from_stdin(raw: str) -> str:
    """Host UserPromptSubmit hooks pipe a JSON payload on stdin; extract the prompt.
    Falls back to the raw string if it isn't JSON (manual `echo ... | omw recall`)."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw[0] in "{[":
        try:
            import json
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k in _PROMPT_KEYS:
                    val = obj.get(k)
                    if isinstance(val, str) and val.strip():
                        return val
                return ""  # JSON payload but no recognizable prompt field
        except (ValueError, TypeError):
            pass
    return raw


_FILE_SIGNAL_RE = __import__("re").compile(
    r"(?i)([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|rs|go|rb|java|sh|ya?ml|json|toml|md|sql))")
_ERROR_SIGNAL_RE = __import__("re").compile(
    r"(?i)\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)|Traceback|panic|fatal)\b")


def _signal_queries(text: str) -> list[str]:
    """One focused follow-up query for error/file prompts, like mem0's trigger rubric."""
    signals: list[str] = []
    signals.extend(_ERROR_SIGNAL_RE.findall(text or ""))
    for path in _FILE_SIGNAL_RE.findall(text or ""):
        signals.extend(__import__("re").findall(r"[A-Za-z0-9가-힣_-]+", path))
    generic = {"src", "scripts", "tests", "test", "py", "ts", "tsx", "js", "md"}
    focused = []
    for token in signals:
        if token.lower() not in generic and token not in focused:
            focused.append(token)
    query = " ".join(focused[:6]).strip()
    return [query] if query and query.lower() != (text or "").strip().lower() else []


def _recall_body(cfg: dict, text: str) -> str:
    """The read-side recall output (extracted verbatim from the old prompt()). Empty
    string means 'no recall injection' (mode=off, auto-miss, or no strong hit)."""
    if cfg["mode"] == "off":
        return ""
    # Resolve the configured retrieval strategy. quiet=True: this runs on every
    # prompt — stay silent (setup warns once).
    strat = effective_strategy(cfg.get("strategy", "fts"), quiet=True)
    # llm is advisory-natured: the hook delegates to the agent and injects no hook-side
    # grounding regardless of mode (mode=off and is_trivial are handled by prompt()). No Python search here.
    if strat == "llm":
        return render_llm_guidance(cfg.get("llm_submode", "route"))
    top_k = int(cfg["top_k"])
    hits = _hits(text, top_k)
    if followups := _signal_queries(text):
        by_path = {h["relpath"]: h for h in hits}
        for query in followups[:1]:
            for hit in _hits(query, top_k):
                old = by_path.get(hit["relpath"])
                if old is None or float(hit.get("score") or 0) > float(old.get("score") or 0):
                    by_path[hit["relpath"]] = hit
        hits = sorted(
            by_path.values(), key=lambda h: float(h.get("score") or 0), reverse=True
        )[:top_k]
    threshold = score_threshold(cfg, strat)
    strong = [h for h in hits if (h.get("score") or 0) >= threshold]
    if strong:  # Tier 2 — concrete grounding
        _record_use([h["relpath"] for h in strong])
        lines = [
            f"<{MARKER}> The active omw wiki has relevant pages. "
            "Use them as evidence and sources for your answer:"
        ]
        for h in strong:
            tags = ",".join(h.get("tags") or [])
            tag_s = f" [{tags}]" if tags else ""
            lines.append(f"- {h.get('title') or h['relpath']} — `{h['relpath']}`{tag_s} (score {h.get('score')})")
        lines.append("Open: `omw view <slug>`. When citing a page, include its citations.")
        lines.append(f"</{MARKER}>")
        return "\n".join(lines)
    if cfg["mode"] == "advisory":  # Tier 1 nudge only when no strong hit
        return (
            f"<{MARKER}> For project or domain facts, check the active wiki first with "
            f"`omw find \"<key nouns>\"`. Ignore this for unrelated requests. </{MARKER}>"
        )
    return ""  # auto + no strong hit → stay silent


_RESUME_RE = __import__("re").compile(
    r"(?i)(where (?:did )?(?:we|i) (?:leave|left) off|pick up where|resume (?:from|where)|"
    r"continue from (?:where|last)|what were we (?:working|doing)|"
    r"어디까지|이어서 (?:진행|작업|해|구현)|지난 (?:작업|세션)|하던 (?:작업|일)|맥락.*복구)"
)


def _is_resume_prompt(text: str) -> bool:
    return bool(_RESUME_RE.search(text or ""))


def _read_hook_payload() -> dict:
    import json
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except (OSError, ValueError):
        # Library callers and pytest capture may expose a non-readable stdin.
        raw = ""
    try:
        obj = json.loads(raw) if raw.strip().startswith("{") else {}
        return obj if isinstance(obj, dict) else {}
    except (ValueError, TypeError):
        return {}


def _session_context(payload: dict | None) -> str:
    try:
        from pathlib import Path
        from scripts import session_capture
        from scripts.paths import registry_path
        cfg = _cfg()
        if not cfg.get("session_capture"):
            return ""
        db = registry_path()
        if not Path(db).exists():
            return ""
        payload = payload if isinstance(payload, dict) else {}
        row = session_capture.latest_context(
            db,
            project_root=payload.get("cwd") or str(Path.cwd()),
            session_id=payload.get("session_id"),
        )
        return session_capture.render_context(row)
    except Exception:
        return ""


def _candidate_context(payload: dict | None) -> str:
    """Stage prior-session candidates at SessionStart and show a bounded notice."""
    try:
        from pathlib import Path
        from scripts import knowledge_candidates
        from scripts.paths import registry_path
        payload = payload if isinstance(payload, dict) else {}
        root = payload.get("cwd") or str(Path.cwd())
        db = registry_path()
        if not db.exists():
            return ""
        active = _active(db)
        mode = knowledge_candidates.effective_mode(
            db, project_root=root, host=payload.get("host"),
            vault_id=active["id"] if active else None,
        )
        if mode == "off":
            return ""
        if mode in {"staged", "auto-raw"}:
            knowledge_candidates.process_pending(
                db,
                project_root=root,
                exclude_session_id=payload.get("session_id"),
                mode=mode,
            )
            return knowledge_candidates.render_notice(db, project_root=root)
        # Advisory mode deliberately avoids classification/search work.
        return (
            "<omw-candidates> Session knowledge-candidate mode is advisory. "
            "OMW will not classify or write session knowledge automatically. "
            "Run `omw candidates run` when you want to prepare a review batch. "
            "</omw-candidates>"
        )
    except Exception:
        return ""


def prompt(
    text: str | None, payload: dict | None = None, *, host: str | None = None,
) -> str:
    """Per-prompt recall + optional capture cue. Returns injectable context (maybe empty).

    is_trivial gates BOTH sides. The `capture` toggle (ON by default) is independent of
    recall.mode: when on AND an active vault exists, the write-side cue is appended (or
    emitted alone if the recall body is empty), so a durable fact the user just stated
    still gets a save nudge even on an FTS miss or with recall.mode=off. When capture is
    off, behavior is byte-identical to the pre-capture recall."""
    cfg = _cfg()
    # Capture-off fast path: preserve the pre-capture behavior exactly, including NOT
    # reading stdin when recall is fully off (mode=off short-circuited before stdin).
    if cfg["mode"] == "off" and not cfg.get("capture"):
        return ""
    if payload is None and text is None:
        payload = _read_hook_payload()
    if text is None:
        text = _prompt_from_stdin(__import__("json").dumps(payload or {}, ensure_ascii=False))
    text = text or ""
    candidate = ""
    if host == "hermes" and isinstance(payload, dict) and payload.get("session_id"):
        candidate = _candidate_context({**payload, "host": "hermes"})
    resume = _is_resume_prompt(text)
    if is_trivial(text) and not resume:
        return candidate
    body = _recall_body(cfg, text)
    if resume:
        session = _session_context(payload)
        if session:
            body = f"{body}\n{session}" if body else session
    if not cfg.get("capture"):
        cue = ""
    elif not _has_active_vault():
        # Capture is on by default, but only nudge to ingest when there's actually a
        # wiki to capture into — a brand-new/vault-less install shouldn't be told to
        # save into a wiki that doesn't exist yet (symmetric with preamble's guard).
        cue = ""
    else:
        cue = render_capture_cue()
    if cue:
        body = f"{body}\n{cue}" if body else cue
    # Hermes has no context-injecting SessionStart/PreCompact event. Its first
    # pre_llm_call therefore stages only captures from older session ids. Repeated
    # prompts in the current session stay cheap because that session is excluded.
    if candidate:
        body = f"{body}\n{candidate}" if body else candidate
    return body


def _base_preamble() -> str:
    """Session-start wiki context: active vault + recent pages."""
    from scripts.paths import registry_path
    db = registry_path()
    if not db.exists():
        return ""
    v = _active(db)
    if not v:
        return ""
    lines = [
        f"<omw-wiki> Active wiki: {v['name']} ({v['mode']}/{v['type']}). "
        "For relevant questions, check the wiki first with `omw find`."
    ]
    try:
        from scripts import hot_cache
        recent = hot_cache._recent_notes(db, v["id"], 5)
        titles = [r.get("title") or r.get("relpath") for r in recent if r.get("title") or r.get("relpath")]
        if titles:
            lines.append("Recent pages: " + ", ".join(titles))
    except Exception:
        pass
    try:
        from datetime import date
        st = maint.status(db, vault_id=v["id"], today=date.today().isoformat())
        if st.get("nudge"):
            lines.append("Maintenance: " + st["nudge"])
    except Exception:
        pass
    try:
        from datetime import date
        from scripts import review
        due = review.due_pages(db, vault_id=v["id"], today=date.today().isoformat(),
                               include_unscheduled=False)[:3]
        names = [d.get("title") or d.get("relpath") for d in due if d.get("title") or d.get("relpath")]
        if names:
            lines.append("Review due: " + ", ".join(names))
    except Exception:
        pass
    lines.append("</omw-wiki>")
    return "\n".join(lines)


def preamble(payload: dict | None = None) -> str:
    """Session-start wiki context plus the latest same-project staged session."""
    if payload is None:
        payload = _read_hook_payload()
    parts = [part for part in (
        _base_preamble(), _session_context(payload), _candidate_context(payload)
    ) if part]
    return "\n".join(parts)


def render_llm_guidance(submode: str) -> str:
    """Agent-delegated retrieval guidance for the `llm` strategy. The hook runs NO
    model — it tells the in-loop agent how to retrieve. Unknown submode → route."""
    if submode == "generative":
        body = (
            "For project or domain questions, run `omw find \"<key nouns>\"` first, "
            "**read the candidate pages and keep only the genuinely relevant ones**, then "
            "answer from that evidence. Do not trust snippet or keyword matches alone. If the "
            "wiki has no supporting evidence, say so. Ignore this for unrelated requests. "
            "When citing a page, include its citations."
        )
    else:  # route (default)
        body = (
            "For project or domain questions, decide whether the question calls for keyword "
            "search (proper nouns or exact terms) or semantic search (concepts or synonyms). "
            "Then search appropriately with `omw find \"<key nouns>\"` and answer from that "
            "evidence. Ignore this for unrelated requests. When citing a page, include its "
            "citations."
        )
    return f"<{MARKER}> {body} </{MARKER}>"


def render_capture_cue() -> str:
    """Per-prompt write-side cue (mem0's write-trigger analog). Guidance only — the
    in-loop agent judges whether the user *stated* durable new info. Routes into the
    existing ingest/gate machinery and the duplicate-ingest confirm class; never
    auto-ingests. Suppressed by is_trivial and gated by the `capture` toggle in prompt()."""
    return (
        f"<{CAPTURE_MARKER}> If the user *states* a durable new fact, decision, or preference "
        f"(rather than asking a question), treat it as a save signal, not a search signal. "
        f"Offer to capture it with `omw ingest <source>` or `omw gate note ingest`. Do not "
        f"write it immediately: first ask whether to add it to the wiki using the "
        f"duplicate-ingest confirmation class. Ignore this for unrelated requests. "
        f"</{CAPTURE_MARKER}>"
    )


def render_recall_block(mode: str = "auto") -> str:
    """Tier 1 guidance block for host instruction files (CLAUDE.md/AGENTS.md/GEMINI.md)."""
    return "\n".join([
        f"<!-- {MARKER}:start -->",
        "## omw wiki recall (managed by `omw setup recall` — do not edit between markers)",
        "",
        f"This workspace has an omw wiki (recall mode: {mode}). Before answering:",
        "- **CHECK WHEN**: the user refers to prior notes, decisions, or something \"in the wiki\"; asks about domain or project facts; or requests a non-trivial decision.",
        "- **SKIP WHEN**: general knowledge or grammar; a simple acknowledgement or continuation; or the user *states a new fact* (which is an ingest candidate instead).",
        "- **HOW**: search with `omw find \"<key nouns>\"`; when citing a page, include its citations.",
        f"<!-- {MARKER}:end -->",
    ])


ALWAYS_ON_MARKER = "omw-wiki-first"


def render_always_on_block() -> str:
    """Persistent 'wiki-first' instruction for host files (CLAUDE.md/AGENTS.md).
    Soft enforcement: nudges the agent to consult the wiki before raw search.
    Distinct marker from the recall block so both can coexist + update independently."""
    m = ALWAYS_ON_MARKER
    return "\n".join([
        f"<!-- {m}:start -->",
        "## omw wiki-first (managed by `omw setup agents` — do not edit between markers)",
        "",
        "This workspace has a compiled omw wiki. For domain or project knowledge questions:",
        "- Check the wiki **first** with `omw find \"<key nouns>\"` before answering.",
        "- Before grepping or reading `raw/` directly, check whether the wiki already organizes "
        "the same material (the wiki is the primary source of context; raw files are sources).",
        "- When citing a page, include its citations.",
        f"<!-- {m}:end -->",
    ])


def upsert_block(md_path, block: str, marker: str = MARKER) -> None:
    """Insert/replace a marker region in md_path (idempotent).

    Uses *marker* to build the start/end fences (defaults to the module-level
    MARKER so existing callers need no changes).
    """
    from pathlib import Path
    p = Path(md_path)
    start, end = f"<!-- {marker}:start -->", f"<!-- {marker}:end -->"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if start in text and end in text:
        new = text[: text.index(start)] + block + text[text.index(end) + len(end):]
    else:
        sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        new = text + sep + block + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")


#: tools whose target we inspect for a raw/ read so we can nudge toward the wiki.
_READ_TOOLS = {
    "read", "grep", "glob", "cat", "search",
    # Codex and some Claude-compatible hosts expose shell reads under these names.
    "bash", "shell", "exec", "exec_command", "functions.exec",
}

_PRETOOL_INPUT_KEYS = ("path", "file_path", "pattern", "glob", "query", "command", "cmd")


def _targets_raw(tool_input: dict) -> bool:
    """True if a read/grep payload points into the vault's raw/ sources."""
    for key in _PRETOOL_INPUT_KEYS:
        val = tool_input.get(key)
        if isinstance(val, str) and "raw/" in val:
            return True
    return False


def _pretool_path_query(payload: dict) -> str:
    import re
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        return ""
    values = [tool_input.get(k) for k in _PRETOOL_INPUT_KEYS]
    text = " ".join(v for v in values if isinstance(v, str))
    tokens = [t for t in re.findall(r"[A-Za-z0-9가-힣_-]+", text) if
              t.lower() not in {"raw", "wiki", "src", "scripts", "tests", "test", "md", "py",
                                "ts", "tsx", "js", "json", "yaml", "yml"}]
    return " ".join(tokens[-6:])


def _pretool_path_hits(payload: dict) -> list[dict]:
    """Fast FTS-only lookup for a file target; never cold-start an embedder."""
    query = _pretool_path_query(payload)
    if not query:
        return []
    try:
        from scripts import search_index
        from scripts.paths import registry_path
        db = registry_path()
        v = _active(db)
        if not v:
            return []
        hits = search_index.query(db, vault_id=v["id"], query=normalize_query(query), limit=3)
        return [h for h in hits if float(h.get("score") or 0) >= 3.0]
    except Exception:
        return []


def pretool(payload: dict | None) -> str:
    """Inject relevant wiki pages before file reads, plus the stronger raw/ nudge."""
    try:
        if not isinstance(payload, dict):
            payload = _read_pretool_stdin()
        tool = str(payload.get("tool_name") or payload.get("tool") or "").lower()
        if tool not in _READ_TOOLS:
            return ""
        if not _has_active_vault():
            return ""
        parts = []
        tool_input = payload.get("tool_input") or payload.get("input") or {}
        if _targets_raw(tool_input):
            parts.append(
                "Before reading `raw/` directly, try `omw find \"<key nouns>\"` first; "
                "the wiki may already organize the same material and is the primary source of context.")
        hits = _pretool_path_hits(payload)
        if hits:
            lines = ["Related wiki pages for this file operation:"]
            lines.extend(f"- {h.get('title') or h['relpath']} — `{h['relpath']}`"
                         for h in hits)
            lines.append("Use these only when they are genuinely relevant to the operation.")
            parts.append("\n".join(lines))
        return f"<{MARKER}> " + "\n".join(parts) + f" </{MARKER}>" if parts else ""
    except Exception:
        return ""


def _read_pretool_stdin() -> dict:
    return _read_hook_payload()


def _capture_debug(result: dict) -> dict:
    """Opt-in reason-only diagnostics; never prints captured session content."""
    import json
    import os
    if os.environ.get("OMW_CAPTURE_DEBUG"):
        print(json.dumps(result), file=sys.stderr)
    return result


def capture_session(*, host: str, source: str, payload: dict | None = None) -> dict:
    """Store a bounded local snapshot and never promote it into a vault."""
    try:
        from scripts import registry, session_capture
        from scripts.paths import registry_path
        if not _cfg().get("session_capture"):
            return _capture_debug({"stored": False, "reason": "disabled"})
        if payload is None:
            payload = _read_hook_payload()
        db = registry_path()
        registry.init_db(db)
        result = session_capture.capture(db, payload, host=host, source=source)
        from scripts import knowledge_candidates
        active = registry.get_active(db)
        project_root = (
            (payload or {}).get("cwd") or str(__import__("pathlib").Path.cwd())
        )
        candidate_mode = knowledge_candidates.effective_mode(
            db, project_root=project_root, host=host,
            vault_id=active["id"] if active else None,
        )
        if source == "precompact" and candidate_mode in {"staged", "auto-raw"}:
            try:
                result["candidate_batch"] = knowledge_candidates.process_pending(
                    db,
                    project_root=project_root,
                    session_id=(payload or {}).get("session_id"),
                    mode=candidate_mode,
                )
            except Exception:
                result["candidate_batch"] = {"ok": False, "reason": "error"}
        return _capture_debug(result)
    except Exception:
        return _capture_debug({"stored": False, "reason": "error"})


def session_captures(*, limit: int = 20) -> list[dict]:
    try:
        from scripts import session_capture
        from scripts.paths import registry_path
        return session_capture.list_captures(registry_path(), limit=limit)
    except Exception:
        return []


def dismiss_session(capture_id: int) -> bool:
    try:
        from scripts import session_capture
        from scripts.paths import registry_path
        return session_capture.dismiss(registry_path(), capture_id)
    except Exception:
        return False


#: Each supported host reads command hooks from this JSON file, all sharing the
#: Claude-style schema: {"hooks": {<Event>: [{"hooks": [{"type","command",...}]}]}}.
def _hook_home():
    """Home root for host hook configs. Honors OMW_HOOK_HOME so tests (and sandboxes)
    never write to the real ~/.claude, ~/.codex, ~/.openclaw, etc."""
    import os
    from pathlib import Path
    return Path(os.environ.get("OMW_HOOK_HOME") or Path.home())


def host_hook_configs() -> dict:
    """JSON-mechanism hosts → their hook config path. Derived from the hosts.HOOK SSOT
    (claude/codex/gemini). hermes (yaml) and opencode/openclaw (ts-plugin) are wired by
    their own writers, not this map."""
    from scripts import hosts
    home = _hook_home()
    out = {}
    for host, d in hosts.HOOK.items():
        if d.get("mech") == "json" and d.get("path"):
            out[host] = home / d["path"].replace("~/", "")
    return out


def _omw_bin() -> str:
    """Resolve the CLI recorded in generated hooks.

    Prefer an explicit override, then the executable that launched this setup
    process. This prevents a stale `omw` earlier on PATH from being baked into
    a live host hook while a newer installation is running `omw setup`.
    """
    import os
    import shutil
    from pathlib import Path
    if configured := os.environ.get("OMW_BIN"):
        return configured
    invoked = Path(sys.argv[0]).expanduser()
    if invoked.name == "omw" and invoked.exists():
        return str(invoked.resolve())
    return shutil.which("omw") or "omw"


def _format_output(out: str, fmt: str, event: str) -> str:
    """Wrap a recall body in the stdout shape the host's hook system expects.
    JSON hosts must receive a JSON object even when recall has no context; an empty
    stdout stream is rejected as malformed hook output by current Claude and Codex."""
    import json
    if not out and fmt in {"claude-json", "codex-json", "gemini-json"}:
        return json.dumps({"continue": True})
    if not out:
        return ""
    if fmt in {"claude-json", "codex-json", "gemini-json"}:
        return json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                                  "additionalContext": out}}, ensure_ascii=False)
    if fmt == "hermes-json":
        return json.dumps({"context": out}, ensure_ascii=False)
    return out  # plain


#: abstract event -> (recall verb, statusMessage). 'omw recall' substring marks idempotency.
_RECALL_VERBS = {
    "session": ("preamble", "omw wiki preamble"),
    "prompt": ("prompt", "omw wiki recall"),
    "pretool": ("pretool", "omw wiki-first nudge"),
}

# Cold starts need more headroom than ordinary tool hooks. Prompt recall may
# open the search index, while the session preamble and pre-tool nudge are small.
_RECALL_TIMEOUTS = {"session": 10, "prompt": 15, "pretool": 5}
_WATCHDOG_TIMEOUTS = {"session": 8, "prompt": 12, "pretool": 4}
_CAPTURE_SOURCES = {"precompact": "precompact", "turnend": "stop"}


def _watched_recall_command(omw: str, verb: str, fmt: str, event: str,
                            timeout: int) -> str:
    """Shell-safe internal wrapper with a deadline below the host timeout."""
    import shlex
    python = shlex.quote(sys.executable)
    argv = " ".join(shlex.quote(str(v)) for v in (
        omw, "recall", verb, "--format", fmt, "--event", event,
    ))
    return f"{python} -m scripts.hook_watchdog --timeout {timeout} -- {argv}"


def _recall_hook_specs(host: str = "claude") -> dict:
    """Concrete event -> (command, statusMessage, timeout) derived from the
    hosts.HOOK descriptor. Only the events in the host's `recall` list are wired (events
    that actually inject context). Each command bakes in the per-event `--format` and the
    host's `--event` so `omw recall` emits the right stdout shape under the right event."""
    from scripts import hosts
    omw = _omw_bin()
    specs = {}
    for abstract in hosts.hook_recall_events(host):
        verb, status = _RECALL_VERBS[abstract]
        event = hosts.hook_event(host, abstract)
        if not event:
            continue
        fmt = hosts.hook_event_fmt(host, abstract)
        recall_cmd = _watched_recall_command(
            omw, verb, fmt, event, _WATCHDOG_TIMEOUTS[abstract]
        )
        # A successful process is insufficient for JSON hooks: an empty body (or
        # unexpected stdout) still makes the host reject the hook. Capture stdout,
        # forward it only when it is a non-empty JSON document, and otherwise emit
        # Codex/Claude's accepted no-op object. The final printf also guarantees a
        # zero exit status when a future CLI argument change makes recall fail.
        if fmt in {"claude-json", "codex-json", "gemini-json"}:
            cmd = (
                f'out=$({recall_cmd}); rc=$?; '
                'if [ "$rc" -eq 0 ] && [ -n "$out" ] '
                '&& printf \'%s\' "$out" | jq -e . >/dev/null 2>&1; then '
                'printf \'%s\\n\' "$out"; else printf \'{\"continue\":true}\\n\'; fi'
            )
        else:
            # Plain-output hosts may safely treat an empty result as no injection.
            cmd = f'{recall_cmd} || true'
        specs[event] = (cmd, status, _RECALL_TIMEOUTS[abstract])
    return specs


def _capture_hook_specs(host: str) -> dict:
    """Observation-only lifecycle hooks. They always return a valid JSON no-op."""
    from scripts import hosts
    omw = _omw_bin()
    specs = {}
    for abstract in hosts.hook_capture_events(host):
        event = hosts.hook_event(host, abstract)
        source = _CAPTURE_SOURCES.get(abstract)
        if not event or not source:
            continue
        fmt = hosts.hook_event_fmt(host, abstract)
        recall_cmd = _watched_recall_command(
            omw, "capture", fmt, event, 8
        ) + f" --host {host} --source {source}"
        cmd = (
            f'out=$({recall_cmd}); rc=$?; '
            'if [ "$rc" -eq 0 ] && [ -n "$out" ] '
            '&& printf \'%s\' "$out" | jq -e . >/dev/null 2>&1; then '
            'printf \'%s\\n\' "$out"; else printf \'{"continue":true}\\n\'; fi'
        )
        specs[event] = (cmd, "omw local session capture", 10)
    return specs


def _is_omw_recall_cmd(cmd: str) -> bool:
    return "recall" in cmd and any(
        verb in cmd for verb in ("preamble", "prompt", "pretool", "capture"))


def _strip_omw_recall(hooks: dict) -> bool:
    """Remove omw-recall hooks from ALL events (migration: drops stale commands and hooks
    left under wrong/renamed event keys). Prunes at the individual-hook level — a group that
    mixes an omw hook with a user hook keeps the user hook — then drops emptied groups/events.
    Returns True if anything was removed."""
    changed = False
    for event in list(hooks):
        groups = hooks.get(event) or []
        new_groups = []
        for g in groups:
            inner = (g or {}).get("hooks", [])
            kept_inner = [h for h in inner
                          if not _is_omw_recall_cmd((h or {}).get("command", ""))]
            if len(kept_inner) != len(inner):
                changed = True
                if kept_inner:
                    new_groups.append({**g, "hooks": kept_inner})  # keep user hooks in the group
                # else: group held only omw hooks → drop it
            else:
                new_groups.append(g)
        if new_groups:
            hooks[event] = new_groups
        elif groups:  # we removed the last group(s) — drop the now-empty event
            del hooks[event]
    return changed


def _atomic_write(path, text: str) -> None:
    """Backup-once then write via a temp file + os.replace (atomic; never leaves a half file)."""
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_suffix(path.suffix + ".omw-bak")
        if not bak.exists():
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = path.with_suffix(path.suffix + ".omw-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def wire_host(host: str, *, config_path=None) -> tuple[bool, str]:
    """Wire a host's native recall hooks (JSON mechanism). Rebuilds omw-owned hooks: strips
    any existing omw-recall entries from every event (migrating away stale formats / renamed
    events), then inserts the host's correct event set + per-event `--format`. Preserves all
    non-omw content. Idempotent (no write when already correct). Returns (changed, detail)."""
    import json
    from pathlib import Path
    path = Path(config_path) if config_path else host_hook_configs().get(host)
    if path is None:
        return False, f"unknown host {host!r}"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as e:
        return False, f"unreadable {path}: {e}"
    if not isinstance(data, dict):
        return False, f"unexpected config shape in {path}"
    before = json.dumps(data, sort_keys=True)
    hooks = data.setdefault("hooks", {})
    _strip_omw_recall(hooks)  # migration: clear all omw-recall hooks first
    added = []
    specs = {**_recall_hook_specs(host), **_capture_hook_specs(host)}
    for event, (command, status, timeout) in specs.items():
        hooks.setdefault(event, []).append(
            {"hooks": [{"type": "command", "command": command,
                        "timeout": timeout, "statusMessage": status}]})
        added.append(event)
    if not data.get("hooks"):  # don't leave an empty hooks block
        data.pop("hooks", None)
    if json.dumps(data, sort_keys=True) == before:
        return False, f"already wired ({path})"
    try:
        _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    except OSError as e:
        return False, f"write failed {path}: {e}"
    return True, f"wired {'+'.join(added)} → {path}"


def _hermes_config_path(profile: str | None):
    """Profile config.yaml the hermes CLI/gateway reads. Verified on disk: the real file
    is `config.yaml` (docs alternate with `cli-config.yaml`, which does not exist)."""
    from scripts import hermes_detect
    root = hermes_detect.hermes_home()
    if profile and profile != "main":
        return root / "profiles" / profile / "config.yaml"
    return root / "config.yaml"


def wire_hermes(*, profile=None, config_path=None, allowlist_path=None) -> tuple[bool, str]:
    """Wire recall injection and observation capture into a Hermes profile.

    Hermes' only context-injecting hook is `pre_llm_call` (verified: on_session_start /
    post_llm_call are observe-only). OMW injects per-prompt recall there and stages older
    session captures when a new session id appears. `post_llm_call` only stores a bounded,
    redacted capture. Both hooks pre-seed the first-use consent allowlist so they register
    in non-TTY (gateway/cron) contexts. Idempotent; preserves existing YAML."""
    import json
    from pathlib import Path
    import yaml
    if config_path is None and profile is None:
        # Default to the active profile (mirrors instruction-injection scoping); the docs'
        # profile config is ~/.hermes/profiles/<p>/config.yaml.
        try:
            from scripts import hosts
            profile = hosts.active_profile()
        except Exception:
            profile = None
    path = Path(config_path) if config_path else _hermes_config_path(profile)
    omw = _omw_bin()
    command = f'"{omw}" recall prompt --format hermes-json --host hermes || true'
    capture_command = (
        f'"{omw}" recall capture --format hermes-json --event post_llm_call '
        "--host hermes --source stop || true"
    )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, yaml.YAMLError) as e:
        return False, f"unreadable {path}: {e}"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return False, f"unexpected config shape in {path}"
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("pre_llm_call", [])
    changed = False
    old_prompt = [
        entry for entry in entries
        if "recall prompt" in (entry or {}).get("command", "")
    ]
    if (
        len(old_prompt) != 1
        or old_prompt[0].get("command") != command
        or old_prompt[0].get("timeout") != 10
    ):
        entries[:] = [
            entry for entry in entries
            if "recall prompt" not in (entry or {}).get("command", "")
        ]
        entries.append({"command": command, "timeout": 10})
        changed = True
    capture_entries = hooks.setdefault("post_llm_call", [])
    old_capture = [
        entry for entry in capture_entries
        if "recall capture" in (entry or {}).get("command", "")
    ]
    if (
        len(old_capture) != 1
        or old_capture[0].get("command") != capture_command
        or old_capture[0].get("timeout") != 10
    ):
        capture_entries[:] = [
            entry for entry in capture_entries
            if "recall capture" not in (entry or {}).get("command", "")
        ]
        capture_entries.append({"command": capture_command, "timeout": 10})
        changed = True
    if not changed:
        return False, f"already wired ({path})"
    try:
        _atomic_write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    except OSError as e:
        return False, f"write failed {path}: {e}"
    # Pre-seed the consent allowlist (keyed on the exact command string).
    if allowlist_path:
        allow = Path(allowlist_path)
    else:
        from scripts import hermes_detect
        allow = hermes_detect.hermes_home() / "shell-hooks-allowlist.json"
    try:
        adata = json.loads(allow.read_text(encoding="utf-8")) if allow.exists() else {}
        if not isinstance(adata, dict):
            adata = {}
        approvals = adata.setdefault("approvals", [])
        approvals[:] = [
            approval for approval in approvals
            if not (
                approval.get("event") in {"pre_llm_call", "post_llm_call"}
                and any(
                    verb in approval.get("command", "")
                    for verb in ("recall prompt", "recall capture")
                )
            )
        ]
        for event, approved_command in (
            ("pre_llm_call", command), ("post_llm_call", capture_command),
        ):
            if not any(a.get("command") == approved_command and a.get("event") == event
                       for a in approvals):
                approvals.append({"event": event, "command": approved_command})
        adata["approvals"] = approvals
        _atomic_write(allow, json.dumps(adata, indent=2, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass  # allowlist pre-seed is best-effort; hermes will prompt on first use
    return True, f"wired pre_llm_call+post_llm_call → {path}"


# TS plugin templates. opencode and openclaw use a JS/TS plugin event API (not shell
# hooks), so omw ships a thin plugin that shells out to `omw recall` and injects the result
# through each runtime's available surface.
_OPENCODE_PLUGIN_TS = '''\
// omw-recall — auto-loaded opencode plugin. Injects omw wiki context into the system
// prompt via the experimental transform (opencode has no AI-visible message injection
// today — see github.com/anomalyco/opencode/issues/17412), so this is best-effort.
import type { Plugin } from "@opencode-ai/plugin"

export const OmwRecall: Plugin = async ({ $ }) => {
  return {
    "experimental.chat.system.transform": async (_input: any, output: any) => {
      try {
        const res = await $`omw recall preamble --format plain`.quiet().nothrow()
        const text = (res.stdout?.toString() ?? "").trim()
        if (text) output.system.push("<omw-wiki>\\n" + text + "\\n</omw-wiki>")
      } catch (_e) { /* recall is best-effort; never block the session */ }
    },
  }
}
'''

_OPENCLAW_PLUGIN_TS = '''\
// omw-recall — OpenClaw plugin. Injects omw wiki context at before_prompt_build via the
// typed prependContext return (the supported injection surface).
import { execFile } from "node:child_process"
import { promisify } from "node:util"
const run = promisify(execFile)

export default {
  id: "omw-recall",
  register(api: any) {
    api.on("before_prompt_build", async (_event: any) => {
      try {
        const { stdout } = await run("omw", ["recall", "prompt", "--format", "plain"])
        const text = (stdout || "").trim()
        if (text) return { prependContext: text }
      } catch (_e) { /* best-effort; never block the turn */ }
      return
    }, { priority: 50 })
  },
}
'''


def _ts_plugin_dest(host: str, *, base_dir=None, workspace=None):
    home = _hook_home()
    if host == "opencode":
        return home / ".config" / "opencode" / "plugin" / "omw-recall.ts"
    if host == "openclaw":
        return home / ".openclaw" / "plugins" / "omw-recall" / "index.ts"
    return None


def wire_ts_plugin(host: str, *, dest=None, config_path=None,
                   base_dir=None, workspace=None) -> tuple[bool, str]:
    """Install the bundled omw-recall TS plugin for a plugin-based host.

    opencode: drop an auto-loaded plugin file (no registration needed).
    openclaw: drop the plugin file AND register it in openclaw.json (plugins.entries).
    Idempotent: skips if the plugin file already exists. Returns (changed, detail)."""
    import json
    from pathlib import Path
    path = Path(dest) if dest else _ts_plugin_dest(host, base_dir=base_dir, workspace=workspace)
    if path is None:
        return False, f"no TS plugin for host {host!r}"
    content = _OPENCODE_PLUGIN_TS if host == "opencode" else _OPENCLAW_PLUGIN_TS
    # Plugin-file idempotency is tracked separately from openclaw.json registration so a
    # pre-existing plugin file never leaves openclaw unregistered (B5).
    file_present = path.exists() and "omw-recall" in path.read_text(encoding="utf-8")
    changed = False
    if not file_present:
        try:
            _atomic_write(path, content)
            changed = True
        except OSError as e:
            return False, f"write failed {path}: {e}"
    if host == "opencode":  # auto-loaded; no registration step
        return (changed, f"installed {path}" if changed else f"already installed ({path})")
    # openclaw: ALWAYS ensure registration in openclaw.json (even if the plugin file existed).
    cfg = Path(config_path) if config_path else (_hook_home() / ".openclaw" / "openclaw.json")
    desired = {"enabled": True, "hooks": {"allowConversationAccess": True}}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        if not isinstance(data, dict):
            return changed, f"installed {path} (openclaw.json unexpected shape; not registered)"
        entries = data.setdefault("plugins", {}).setdefault("entries", {})
        if entries.get("omw-recall") != desired:
            entries["omw-recall"] = desired
            _atomic_write(cfg, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            changed = True
    except (OSError, ValueError) as e:
        return changed, f"installed {path} (registration failed: {e})"
    return changed, (f"installed + registered {path}" if changed
                     else f"already installed ({path})")


def main(argv=None) -> int:
    """Compatibility entrypoint; the top-level CLI owns the recall argument schema."""
    from scripts import omw_cli
    args = list(sys.argv[1:] if argv is None else argv)
    return omw_cli.main(["recall", *args])


if __name__ == "__main__":
    raise SystemExit(main())
