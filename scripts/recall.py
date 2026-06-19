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

MARKER = "omw-recall"

#: retrieval strategies (축 2). Only `fts` is implemented; the rest are planned
#: and fall back to `fts` (see references/auto-recall-hook-design.md §10).
STRATEGIES = ("fts", "embedding", "hybrid", "llm")
LLM_SUBMODES = ("route", "generative")
_IMPLEMENTED_STRATEGIES = {"fts"}

# min_score=1.0: the FTS scorer ranks on frontmatter (title/tags/summary/relpath),
# not body — so ~1.0 means at least one meaningful token hit. Pages with a good
# `summary` rank higher; bump min_score if recall feels noisy.
_DEFAULTS = {"mode": "auto", "strategy": "fts", "llm_submode": "route",
             "min_score": 1.0, "top_k": 3, "snippet_chars": 280}


def effective_strategy(strategy: str, *, quiet: bool = False) -> str:
    """Resolve the configured strategy to one that's implemented. Unimplemented
    strategies (embedding/hybrid/llm) gracefully fall back to fts — so users can
    already *select* the mode before the engines land. `quiet=True` on the
    per-prompt hot path (the wizard already warns once at config time); the note
    is only useful on explicit `omw recall`/setup invocations."""
    if strategy in _IMPLEMENTED_STRATEGIES:
        return strategy
    if strategy in STRATEGIES and not quiet:
        print(f"omw recall: strategy '{strategy}' is planned, not implemented yet "
              f"— using 'fts'. (references/auto-recall-hook-design.md §10)", file=sys.stderr)
    return "fts"


def cost_warning(mode: str, strategy: str) -> str | None:
    """Flag the expensive combination: an LLM call on every prompt."""
    if mode == "auto" and strategy == "llm":
        return ("주의: mode=auto + strategy=llm은 매 프롬프트마다 별도 LLM 호출이라 비용/지연이 큽니다. "
                "advisory 모드(인루프 에이전트가 수행, 추가 비용 0)를 권장합니다.")
    return None

# Short acknowledgements / continuations that should never trigger recall.
_ACK = {
    "ok", "okay", "k", "y", "yes", "n", "no", "thanks", "thank you", "continue",
    "네", "응", "옙", "ㅇㅋ", "고마워", "계속", "그래", "맞아", "좋아",
}


def _cfg() -> dict:
    try:
        from scripts import config
        raw = (config.load_config() or {}).get("recall") or {}
    except Exception:
        raw = {}
    out = dict(_DEFAULTS)
    for k in ("mode", "strategy", "min_score", "top_k", "snippet_chars"):
        if k in raw:
            out[k] = raw[k]
    llm = raw.get("llm")  # harden: a hand-edited non-dict must not raise here
    out["llm_submode"] = (llm if isinstance(llm, dict) else {}).get("submode", _DEFAULTS["llm_submode"])
    return out


def is_trivial(text: str) -> bool:
    """True for prompts not worth a wiki lookup (too short / pure ack)."""
    t = (text or "").strip()
    return len(t) < 12 or t.lower() in _ACK


def _active(db):
    from scripts import registry
    return registry.get_active(db)


def _strip_josa(token: str) -> str:
    """Drop a trailing Korean postposition so 'ARIMA와'/'평가지표를' match the index.
    Only Hangul-ending tokens, and only when ≥2 chars remain."""
    import re
    if not re.search(r"[가-힣]$", token):
        return token
    from scripts.text_match import _JOSA
    for j in sorted(_JOSA, key=len, reverse=True):
        if token.endswith(j) and len(token) - len(j) >= 2:
            return token[: -len(j)]
    return token


def normalize_query(text: str) -> str:
    """Josa-normalize a free-text prompt for FTS recall (the index tokenizer is
    plain — natural Korean prompts attach josa that would otherwise miss)."""
    return " ".join(_strip_josa(t) for t in (text or "").split())


def _hits(text: str, top_k: int) -> list[dict]:
    from scripts import search_index
    from scripts.paths import registry_path
    db = registry_path()
    if not db.exists():
        return []
    v = _active(db)
    if not v:
        return []
    try:
        return search_index.query(db, vault_id=v["id"], query=normalize_query(text), limit=top_k)
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


def prompt(text: str | None) -> str:
    """Per-prompt recall. Returns injectable context (possibly empty)."""
    cfg = _cfg()
    if cfg["mode"] == "off":
        return ""
    if text is None:
        text = _prompt_from_stdin(sys.stdin.read()) if not sys.stdin.isatty() else ""
    text = text or ""
    if is_trivial(text):
        return ""

    # Resolve the configured retrieval strategy. Today every strategy routes to the
    # fts backend (embedding/hybrid/llm fall back here until their engines land).
    # quiet=True: this runs on every prompt — stay silent (setup warns once).
    effective_strategy(cfg.get("strategy", "fts"), quiet=True)
    hits = _hits(text, int(cfg["top_k"]))
    strong = [h for h in hits if (h.get("score") or 0) >= float(cfg["min_score"])]

    if strong:  # Tier 2 — concrete grounding (both auto and advisory benefit)
        lines = [f"<{MARKER}> 활성 omw 위키에 관련 페이지가 있습니다 — 답변의 근거/출처로 활용하세요:"]
        for h in strong:
            tags = ",".join(h.get("tags") or [])
            tag_s = f" [{tags}]" if tags else ""
            lines.append(f"- {h.get('title') or h['relpath']} — `{h['relpath']}`{tag_s} (score {h.get('score')})")
        lines.append("열기: `omw view <slug>` · 인용 시 페이지의 citations를 함께 제시하세요.")
        lines.append(f"</{MARKER}>")
        return "\n".join(lines)

    if cfg["mode"] == "advisory":  # Tier 1 nudge only when no strong hit
        return (f"<{MARKER}> 프로젝트/도메인 사실이면 답하기 전에 `omw find \"<핵심 명사>\"`로 "
                f"활성 위키를 확인하세요. 무관하면 무시. </{MARKER}>")
    return ""  # auto + no strong hit → stay silent (avoid per-prompt noise)


def preamble() -> str:
    """Session-start context: active vault + recent pages."""
    from scripts.paths import registry_path
    db = registry_path()
    if not db.exists():
        return ""
    v = _active(db)
    if not v:
        return ""
    lines = [f"<omw-wiki> 활성 위키: {v['name']} ({v['mode']}/{v['type']}). "
             f"관련 질문엔 `omw find`로 위키를 먼저 확인하세요."]
    try:
        from scripts import hot_cache
        recent = hot_cache._recent_notes(db, v["id"], 5)
        titles = [r.get("title") or r.get("relpath") for r in recent if r.get("title") or r.get("relpath")]
        if titles:
            lines.append("최근 페이지: " + ", ".join(titles))
    except Exception:
        pass
    lines.append("</omw-wiki>")
    return "\n".join(lines)


def render_recall_block(mode: str = "auto") -> str:
    """Tier 1 guidance block for host instruction files (CLAUDE.md/AGENTS.md/GEMINI.md)."""
    return "\n".join([
        f"<!-- {MARKER}:start -->",
        "## omw wiki recall (managed by `omw setup recall` — do not edit between markers)",
        "",
        f"이 워크스페이스에는 omw 위키가 있습니다 (recall 모드: {mode}). 답하기 전에:",
        "- **확인 WHEN**: 사용자가 과거 정리·결정·\"위키에 있던\" 것을 언급 / 도메인·프로젝트 사실 질문 / 비자명한 의사결정.",
        "- **생략 WHEN**: 일반 상식·문법, 단순 확인/연속, 사용자가 *새 사실을 진술*(→ 오히려 ingest 후보).",
        "- **방법**: `omw find \"<핵심 명사>\"`로 검색하고, 본문 인용 시 페이지의 citations를 함께 제시.",
        f"<!-- {MARKER}:end -->",
    ])


def upsert_block(md_path, block: str) -> None:
    """Insert/replace the omw-recall marker region in md_path (idempotent)."""
    from pathlib import Path
    p = Path(md_path)
    start, end = f"<!-- {MARKER}:start -->", f"<!-- {MARKER}:end -->"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if start in text and end in text:
        new = text[: text.index(start)] + block + text[text.index(end) + len(end):]
    else:
        sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
        new = text + sep + block + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8")


#: Each supported host reads command hooks from this JSON file, all sharing the
#: Claude-style schema: {"hooks": {<Event>: [{"hooks": [{"type","command",...}]}]}}.
def host_hook_configs() -> dict:
    from pathlib import Path
    home = Path.home()
    return {
        "claude": home / ".claude" / "settings.json",
        "codex": home / ".codex" / "hooks.json",
        "gemini": home / ".gemini" / "settings.json",
    }


def _omw_bin() -> str:
    import shutil
    return shutil.which("omw") or "omw"


def _recall_hook_specs() -> dict:
    """event -> (command, statusMessage). Marked by the 'omw recall' substring for idempotency."""
    omw = _omw_bin()
    return {
        "SessionStart": (f'"{omw}" recall preamble', "omw wiki preamble"),
        "UserPromptSubmit": (f'"{omw}" recall prompt', "omw wiki recall"),
    }


def _event_has_recall(entries: list) -> bool:
    """True if any hook in this event is already an `omw recall …` invocation
    (path/quoting-agnostic — matches the `recall preamble|prompt` subcommand)."""
    for group in entries or []:
        for h in (group or {}).get("hooks", []):
            cmd = (h or {}).get("command", "")
            if "recall" in cmd and ("preamble" in cmd or "prompt" in cmd):
                return True
    return False


def wire_host(host: str, *, config_path=None) -> tuple[bool, str]:
    """Idempotently merge recall SessionStart+UserPromptSubmit hooks into a host
    config (JSON). Preserves all existing content. Returns (changed, detail)."""
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
    hooks = data.setdefault("hooks", {})
    added = []
    for event, (command, status) in _recall_hook_specs().items():
        entries = hooks.setdefault(event, [])
        if _event_has_recall(entries):
            continue
        entries.append({"hooks": [{"type": "command", "command": command,
                                   "timeout": 5, "statusMessage": status}]})
        added.append(event)
    if not added:
        return False, f"already wired ({path})"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():  # one-shot backup before first mutation
            bak = path.with_suffix(path.suffix + ".omw-bak")
            if not bak.exists():
                bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as e:
        return False, f"write failed {path}: {e}"
    return True, f"wired {'+'.join(added)} → {path}"


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="omw recall")
    ap.add_argument("action", choices=["preamble", "prompt"])
    ap.add_argument("--text", default=None, help="prompt text (else read stdin)")
    args = ap.parse_args(argv)
    out = preamble() if args.action == "preamble" else prompt(args.text)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
