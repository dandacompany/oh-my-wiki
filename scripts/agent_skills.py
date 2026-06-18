"""Install the OMW skill bundle into agent skill systems (claude/codex/hermes/gemini).

Hybrid: claude/codex/gemini delegate to the `skills` CLI (skills.sh) — global `skills`
if on PATH, else `npx -y skills`; on any failure, fall back to a direct copy of the
local bundle into the agent's skills dir. hermes always direct-copies because its
installer accepts only a single SKILL.md URL (incomplete for OMW's multi-file skill).
Pure stdlib.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ID = "dandacompany/oh-my-wiki@oh-my-wiki"

_AGENT_BINS = {"claude": "claude", "codex": "codex", "hermes": "hermes", "gemini": "gemini"}
_SKILLS_AGENT = {"claude": "claude-code", "codex": "codex", "gemini": "gemini"}
_SKILLS_DIR = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
    "gemini": Path.home() / ".gemini" / "skills",
}
_ORDER = ("claude", "codex", "hermes", "gemini")


def detect_agents() -> list[str]:
    """Installed subset of the supported agents, in stable order."""
    return [a for a in _ORDER if shutil.which(_AGENT_BINS[a])]


_EXCLUDE = {
    "tests", "docs", "docker", ".git", ".github", "node_modules",
    "__pycache__", ".pytest_cache", ".agents", "skills-lock.json", ".DS_Store",
}


def _copy_bundle(dest_skills_dir, *, repo_root=REPO_ROOT) -> Path:
    """Copy the OMW skill (all repo entries except dev/VCS cruft) into
    <dest_skills_dir>/oh-my-wiki/. Idempotent (rmtree then copy)."""
    dest = Path(dest_skills_dir) / "oh-my-wiki"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")
    for src in sorted(Path(repo_root).iterdir()):
        if src.name in _EXCLUDE or src.name.endswith(".egg-info"):
            continue
        if src.is_dir():
            shutil.copytree(src, dest / src.name, ignore=ignore)
        else:
            shutil.copyfile(src, dest / src.name)
    return dest


def _skills_cli_prefix():
    """argv prefix for the skills CLI, or None if neither `skills` nor `npx` is present."""
    if shutil.which("skills"):
        return ["skills"]
    if shutil.which("npx"):
        return ["npx", "-y", "skills"]
    return None


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def _parse_skills_cli_dest(stdout: str) -> str | None:
    """Pull the install path the skills CLI prints (a line like '→ <path>')."""
    for raw in stdout.splitlines():
        line = _ANSI_RE.sub("", raw).strip().strip("│").strip()
        if line.startswith("→") and "/" in line:
            # trailing box-border chars (e.g. "  │") can ride along — strip them too
            return line[1:].strip().rstrip("│ \t").strip()
    return None


def _install_via_skills_cli(agent, *, timeout=300) -> tuple[bool, str | None]:
    """Returns (ok, dest_path). dest_path is the install location if parseable."""
    prefix = _skills_cli_prefix()
    if prefix is None:
        return False, None
    cmd = prefix + ["add", SKILL_ID, "-y", "--copy", "-a", _SKILLS_AGENT[agent]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False, None
    if proc.returncode != 0:
        return False, None
    return True, _parse_skills_cli_dest(getattr(proc, "stdout", "") or "")


def install(agent, *, repo_root=REPO_ROOT, use_skills_cli=True) -> dict:
    """Install OMW into one agent's skill system. Returns a result dict."""
    if agent not in _AGENT_BINS:
        return {"agent": agent, "ok": False, "method": None, "dest": None, "detail": "unknown agent"}
    if agent == "hermes":
        dest = _copy_bundle(_SKILLS_DIR["hermes"], repo_root=repo_root)
        return {"agent": agent, "ok": True, "method": "copy", "dest": str(dest)}
    if use_skills_cli:
        ok, dest = _install_via_skills_cli(agent)
        if ok:
            return {"agent": agent, "ok": True, "method": "skills-cli", "dest": dest}
    dest = _copy_bundle(_SKILLS_DIR[agent], repo_root=repo_root)
    return {"agent": agent, "ok": True, "method": "copy", "dest": str(dest)}


def install_many(agents, *, repo_root=REPO_ROOT, use_skills_cli=True) -> list[dict]:
    """Install into each agent, isolating per-agent failures."""
    results = []
    for a in agents:
        try:
            results.append(install(a, repo_root=repo_root, use_skills_cli=use_skills_cli))
        except Exception as exc:  # one failure must not abort the rest
            results.append({"agent": a, "ok": False, "method": None, "dest": None, "detail": str(exc)})
    return results
