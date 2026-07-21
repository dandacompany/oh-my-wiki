"""Host descriptor SSOT: which instruction file each agent reads, and where.

Two host kinds:
  - "repo"    — instruction file is a working-dir-relative name (claude/codex/
                gemini/opencode). codex and opencode share AGENTS.md.
  - "scoped"  — instruction file lives under the agent's own profile/workspace
                root (hermes → ~/.hermes/profiles/<p>/SOUL.md; openclaw →
                <workspace>/AGENTS.md).
Instruction-injection pickers group repo hosts by their shared file (a
"convention"); skill install stays per-agent (see agent_skills)."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import hermes_detect

# host -> descriptor. `conv` is the convention key used to merge shared-file hosts.
HOSTS: dict[str, dict] = {
    "claude":   {"kind": "repo",   "conv": "claude", "file": "CLAUDE.md"},
    "codex":    {"kind": "repo",   "conv": "agents", "file": "AGENTS.md"},
    "opencode": {"kind": "repo",   "conv": "agents", "file": "AGENTS.md"},
    "gemini":   {"kind": "repo",   "conv": "gemini", "file": "GEMINI.md"},
    "hermes":   {"kind": "scoped", "conv": "hermes", "file": "SOUL.md"},
    "openclaw": {"kind": "scoped", "conv": "openclaw", "file": "AGENTS.md"},
}

# Convention label order for pickers.
_CONV_ORDER = ["claude", "agents", "gemini", "hermes", "openclaw"]


# ── hook descriptor SSOT ─────────────────────────────────────────────────────
# Per-host lifecycle-hook wiring. Each host's hook system differs (verified against
# official docs, 2026-06): event NAMES, config FORMAT, and stdout INJECT FORMAT all
# vary. `events` maps omw's abstract events → the host's concrete event name:
#   session  → inject preamble at session start
#   prompt   → recall on the user's prompt (the primary injection point)
#   pretool  → nudge before a tool reads raw/
#   turnend  → maintenance gate at turn end (a control hook, no injection)
# `mech` selects the writer; `fmt` selects the stdout shape `omw recall` must emit:
#   plain        → bare text (only hosts that explicitly allow it)
#   claude-json  → Claude Code's hookSpecificOutput envelope
#   codex-json   → Codex's compatible hookSpecificOutput envelope
#   gemini-json  → {"hookSpecificOutput": {"hookEventName", "additionalContext"}}
#   hermes-json  → {"context": "..."}
# `recall` lists the abstract events omw auto-wires for context injection on each host —
# ONLY events whose stdout actually reaches the model (verified per docs). E.g. codex/gemini
# do NOT inject on pre-tool, so `pretool` is omitted there (it would be a silent no-op). gate
# (turn-end) is handled separately and stays Claude-only — no other host injects at turn-end.
HOOK: dict[str, dict] = {
    "claude": {
        "mech": "json", "fmt": "claude-json", "path": "~/.claude/settings.json",
        "events": {"session": "SessionStart", "prompt": "UserPromptSubmit",
                   "pretool": "PreToolUse", "turnend": "Stop"},
        "recall": ["session", "prompt", "pretool"],
    },
    "codex": {
        "mech": "json", "fmt": "codex-json", "path": "~/.codex/hooks.json",
        "events": {"session": "SessionStart", "prompt": "UserPromptSubmit",
                   "pretool": "PreToolUse", "turnend": "Stop"},
        "recall": ["session", "prompt"],  # Codex injects only on Session/Prompt
    },
    "gemini": {
        "mech": "json", "fmt": "gemini-json", "path": "~/.gemini/settings.json",
        "events": {"session": "SessionStart", "prompt": "BeforeAgent",
                   "pretool": "BeforeTool", "turnend": "AfterAgent"},
        "recall": ["session", "prompt"],  # BeforeTool injection unconfirmed → omit pretool
    },
    "hermes": {
        # scoped: path resolved at runtime from the active/selected profile.
        "mech": "yaml", "fmt": "hermes-json",
        "events": {"session": "on_session_start", "prompt": "pre_llm_call",
                   "pretool": "pre_tool_call", "turnend": "post_llm_call"},
        "recall": ["prompt"],  # pre_llm_call is hermes' only injecting hook
    },
    "opencode": {"mech": "ts-opencode", "fmt": "plain"},
    "openclaw": {"mech": "ts-openclaw", "fmt": "plain"},
}

#: per-event stdout format override. Claude's PreToolUse injects via the JSON envelope
#: (additionalContext), not plain text — unlike its Session/Prompt events.
_HOOK_FMT_OVERRIDE = {("claude", "pretool"): "claude-json"}


def hook_recall_events(host: str) -> list[str]:
    return list((HOOK.get(host) or {}).get("recall") or [])


def hook_event_fmt(host: str, abstract: str) -> str:
    return _HOOK_FMT_OVERRIDE.get((host, abstract)) or hook_fmt(host)


def hook_mech(host: str) -> str | None:
    return (HOOK.get(host) or {}).get("mech")


def hook_fmt(host: str) -> str:
    return (HOOK.get(host) or {}).get("fmt", "plain")


def hook_event(host: str, abstract: str) -> str | None:
    """Concrete event name for an abstract event (session/prompt/pretool/turnend)."""
    return ((HOOK.get(host) or {}).get("events") or {}).get(abstract)


def is_scoped(host: str) -> bool:
    return HOSTS.get(host, {}).get("kind") == "scoped"


def instruction_choices() -> list[dict]:
    """Convention-level choices for the instruction-injection pickers. Repo hosts
    sharing a file are one entry; scoped hosts are their own entry."""
    by_conv: dict[str, dict] = {}
    for host, d in HOSTS.items():
        c = by_conv.setdefault(d["conv"], {"key": d["conv"], "file": d["file"],
                                           "members": [], "scoped": d["kind"] == "scoped"})
        c["members"].append(host)
    return [by_conv[k] for k in _CONV_ORDER if k in by_conv]


# ── hermes profiles ──────────────────────────────────────────────────────────
def _hermes_root() -> Path:
    return hermes_detect.hermes_home()


def list_profiles() -> list[str]:
    p = _hermes_root() / "profiles"
    return sorted([d.name for d in p.iterdir() if d.is_dir()]) if p.is_dir() else []


def active_profile() -> str | None:
    f = _hermes_root() / "active_profile"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else None


# ── openclaw workspaces ──────────────────────────────────────────────────────
def _openclaw_config() -> dict:
    f = Path.home() / ".openclaw" / "openclaw.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_workspaces() -> list[str]:
    agents = (_openclaw_config().get("agents") or {})
    out: list[str] = []
    for spec in agents.values():
        ws = (spec or {}).get("workspace")
        if ws and ws not in out:
            out.append(ws)
    return out


def default_workspace() -> str | None:
    ws = list_workspaces()
    return ws[0] if ws else None


def resolve_instruction_path(host: str, base_dir, *, profile: str | None = None,
                             workspace: str | None = None) -> Path:
    """Absolute path of the instruction file the host reads.
    repo hosts → base_dir/<file>; hermes → profile SOUL.md; openclaw → workspace AGENTS.md."""
    d = HOSTS.get(host)
    if d is None:
        raise ValueError(f"unknown host: {host!r} (known: {sorted(HOSTS)})")
    if d["kind"] == "repo":
        return Path(base_dir) / d["file"]
    if host == "hermes":
        prof = profile or active_profile()
        if not prof:
            raise ValueError("hermes: no profile given and no active_profile")
        return _hermes_root() / "profiles" / prof / d["file"]
    if host == "openclaw":
        ws = workspace or default_workspace()
        if not ws:
            raise ValueError("openclaw: no workspace given and none configured")
        return Path(ws) / d["file"]
    raise ValueError(f"unhandled scoped host: {host!r}")
