"""Detect which agent host's *session* omw is currently running inside.

This is distinct from two neighbours:
  - `backends.detect_available` probes which agent **CLIs are installed** on PATH
    (and authenticated) so omw can *spawn* one as a subprocess.
  - `hosts.py` enumerates **install targets** (where to write instruction files).

This module answers a third question: "am I, right now, executing *inside* host
X's own agent session?" — so a future dispatch can hand the persona task back to
that host's native subagent mechanism instead of shelling out to a sibling CLI.

Pure env-var sniffing, hermetically testable. Conservative by design: only
well-known session markers are listed, and ambiguous vars that merely indicate a
*companion* integration or an *API key* (not an interactive host session) are
deliberately excluded to avoid false positives.
"""
from __future__ import annotations

import os

from scripts import hermes_detect

# Env vars a host sets *inside its own agent session*. Kept deliberately narrow.
#
# Excluded on purpose (seen in the wild as false-positive traps):
#   - CODEX_COMPANION_SESSION_ID — set by the Codex *companion* plugin while
#     running inside Claude Code; it does NOT mean "this is a Codex host session".
#   - GEMINI_API_KEY — a credential, not a session marker.
_SESSION_MARKERS: dict[str, tuple[str, ...]] = {
    "claude": ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT"),
    "codex": ("CODEX_SANDBOX", "CODEX_SESSION_ID", "CODEX_THREAD_ID"),
    "gemini": ("GEMINI_CLI", "GEMINI_CLI_SESSION", "GEMINI_SESSION_ID"),
    "opencode": ("OPENCODE", "OPENCODE_SESSION", "OPENCODE_SESSION_ID"),
}

# Resolution order when (rarely) more than one marker is present. Hermes is a
# wrapper that can host the others, so it ranks last.
_PRIORITY: tuple[str, ...] = ("claude", "codex", "gemini", "opencode", "hermes")


def in_host_session(host: str, *, env: dict | None = None) -> bool:
    """True iff omw appears to be running inside `host`'s agent session.

    `env` overrides os.environ for hermetic tests."""
    if host == "hermes":
        return hermes_detect.in_hermes_session()
    e = os.environ if env is None else env
    return any(e.get(v) for v in _SESSION_MARKERS.get(host, ()))


def current_host(*, env: dict | None = None) -> str | None:
    """The agent host whose session omw is running inside, or None if undetected.

    Best-effort: an unrecognized host simply returns None (callers must treat
    None as "no native host — use an external backend")."""
    for host in _PRIORITY:
        if in_host_session(host, env=env):
            return host
    return None


def known_hosts() -> tuple[str, ...]:
    """Hosts this module can detect (for messages / tests)."""
    return _PRIORITY
