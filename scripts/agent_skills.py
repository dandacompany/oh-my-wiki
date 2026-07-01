"""Install the OMW skill bundle into agent skill systems (claude/codex/gemini/opencode/hermes/openclaw).

Hybrid: claude/codex/gemini delegate to the `skills` CLI (skills.sh) — global `skills`
if on PATH, else `npx -y skills`; on any failure, fall back to a direct copy of the
local bundle into the agent's skills dir. hermes/opencode/openclaw always direct-copy
because their installers do not support the skills.sh protocol.
Pure stdlib.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from scripts import paths

REPO_ROOT = paths.bundled_root()
SKILL_ID = "dandacompany/oh-my-wiki@oh-my-wiki"

# ── short-alias skill ────────────────────────────────────────────────────────
# No native alias frontmatter key exists in the Agent Skills spec or in
# Claude Code / Codex: `/omw` and `$omw` both resolve by a skill's `name`
# (= its dir). So we ship a thin sibling skill whose name IS `omw`, installed
# next to oh-my-wiki. Generated from this constant (not a repo file) so it is
# present on every install path — dev repo, built wheel `_bundle`, skills CLI,
# direct copy — with zero extra bundling config. The body forwards to the
# canonical skill rather than duplicating its rules (single source of truth).
_ALIAS_NAME = "omw"
_ALIAS_SKILL_MD = """\
---
name: omw
description: Short alias for the oh-my-wiki skill (OMW). Invoke the user's personal LLM-wiki via the omw CLI. Trigger phrases — "omw", "use omw", "/omw", "$omw", "open my wiki", "ingest this", "find a note about X"; Korean "오엠더블유", "오엠더블유 켜줘", "위키 열어줘", "이거 정리해줘". Same skill as oh-my-wiki, just the short name.
argument-hint: "[ingest|query|find|search|vault|lint|status|reindex|list|export] [args]"
---

# omw — short alias for oh-my-wiki

You invoked the **omw** short alias. It is the **same skill as `oh-my-wiki`** — `omw`
is just the short name (and the CLI binary name).

Load and follow the **`oh-my-wiki`** skill now, then carry out the user's request
through the `omw` CLI. All HARD RULES, ops, dispatch logic, and command cards live
in the `oh-my-wiki` skill — do not restate or improvise them here.
"""


def install_alias_into_dir(skills_dir, *, name: str = _ALIAS_NAME) -> Path:
    """Write the short-alias skill to <skills_dir>/<name>/SKILL.md. Idempotent
    (overwrites in place). Returns the alias skill dir."""
    dest = Path(skills_dir) / name
    _clear_stale(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "SKILL.md").write_text(_ALIAS_SKILL_MD, encoding="utf-8")
    return dest

_AGENT_BINS = {"claude": "claude", "codex": "codex", "hermes": "hermes",
               "gemini": "gemini", "opencode": "opencode", "openclaw": "openclaw"}
_SKILLS_AGENT = {"claude": "claude-code", "codex": "codex", "gemini": "gemini"}
_SKILLS_DIR = {
    "claude": Path.home() / ".claude" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
    "gemini": Path.home() / ".gemini" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    # openclaw discovers skills from the shared personal catalog (~/.agents/skills);
    # ~/.openclaw/skills resolves outside its configured root and is skipped.
    "openclaw": Path.home() / ".agents" / "skills",
}
_ORDER = ("claude", "codex", "opencode", "gemini", "hermes", "openclaw")


def detect_agents() -> list[str]:
    """Installed subset of the supported agents, in stable order."""
    return [a for a in _ORDER if shutil.which(_AGENT_BINS[a])]


_EXCLUDE = {
    "tests", "docs", "docker", ".git", ".github", "node_modules",
    "__pycache__", ".pytest_cache", ".agents", "skills-lock.json", ".DS_Store",
    # Dev cruft that must never ship in the skill bundle. Critically, ".claude"
    # holds the repo's own project-local skill install + worktrees — copying it in
    # nests <bundle>/.claude/skills/oh-my-wiki/… so the host's skill scanner
    # recurses over a duplicate tree (770 files / 8.9M → hundreds of stat() storms).
    # "data" is the per-user runtime registry.db — shipping it leaks one user's DB.
    ".claude", ".superpowers", ".ruff_cache", ".mypy_cache", ".venv",
    "data", "dist", "build", ".idea", ".vscode", "uv.lock",
}


def _clear_stale(dest: Path) -> None:
    """Remove whatever sits at `dest` so a fresh mkdir/copy can take its place.

    A symlink (even a *dangling* one left by an earlier install whose target
    moved) makes `mkdir(exist_ok=True)` raise FileExistsError because it is not a
    real directory — `is_symlink()` is True even when the target is gone, so unlink
    it. A regular file is likewise removed; a real directory is rmtree'd."""
    if dest.is_symlink():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        dest.unlink()


def _copy_bundle(dest_skills_dir, *, repo_root=REPO_ROOT) -> Path:
    """Copy the OMW skill (all repo entries except dev/VCS cruft) into
    <dest_skills_dir>/oh-my-wiki/. Idempotent (rmtree then copy)."""
    dest = Path(dest_skills_dir) / "oh-my-wiki"
    _clear_stale(dest)
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


def hermes_profile_targets(hermes_home: Path | None = None) -> list[dict]:
    """Enumerate hermes skill-install targets, one per profile.

    main → <hermes_home>/skills, then one per child dir of <hermes_home>/profiles
    (sorted). Each target: {"name", "skills_dir", "installed"} where installed means
    an oh-my-wiki skill dir already exists there. Degrades to [main] when absent."""
    home = Path(hermes_home) if hermes_home is not None else Path.home() / ".hermes"

    def _target(name: str, skills_dir: Path) -> dict:
        return {"name": name, "skills_dir": skills_dir,
                "installed": (skills_dir / "oh-my-wiki").exists()}

    targets = [_target("main", home / "skills")]
    profiles_dir = home / "profiles"
    if profiles_dir.is_dir():
        for p in sorted(profiles_dir.iterdir(), key=lambda d: d.name):
            if p.is_dir():
                targets.append(_target(p.name, p / "skills"))
    return targets


def install_into_dir(skills_dir, *, repo_root=REPO_ROOT) -> dict:
    """Copy the OMW bundle into <skills_dir>/oh-my-wiki/. Generic over the dir, so it
    serves any per-profile target. Returns a result dict (never raises on copy error).
    On OSError, returns {"ok": False, "method": "copy", "dest": None, "detail": <message>}
    rather than raising."""
    try:
        dest = _copy_bundle(skills_dir, repo_root=repo_root)
        alias = install_alias_into_dir(skills_dir)
        return {"ok": True, "method": "copy", "dest": str(dest),
                "alias_dest": str(alias), "detail": None}
    except OSError as exc:
        return {"ok": False, "method": "copy", "dest": None, "detail": str(exc)}


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
    # The short-alias `omw` skill rides along into the same skills dir, regardless
    # of whether the main skill goes via the skills CLI or a direct copy.
    alias = str(install_alias_into_dir(_SKILLS_DIR[agent]))
    if agent not in _SKILLS_AGENT:
        dest = _copy_bundle(_SKILLS_DIR[agent], repo_root=repo_root)
        return {"agent": agent, "ok": True, "method": "copy", "dest": str(dest),
                "alias_dest": alias}
    if use_skills_cli:
        ok, dest = _install_via_skills_cli(agent)
        if ok:
            return {"agent": agent, "ok": True, "method": "skills-cli", "dest": dest,
                    "alias_dest": alias}
    dest = _copy_bundle(_SKILLS_DIR[agent], repo_root=repo_root)
    return {"agent": agent, "ok": True, "method": "copy", "dest": str(dest),
            "alias_dest": alias}


def install_many(agents, *, repo_root=REPO_ROOT, use_skills_cli=True) -> list[dict]:
    """Install into each agent, isolating per-agent failures."""
    results = []
    for a in agents:
        try:
            results.append(install(a, repo_root=repo_root, use_skills_cli=use_skills_cli))
        except Exception as exc:  # one failure must not abort the rest
            results.append({"agent": a, "ok": False, "method": None, "dest": None, "detail": str(exc)})
    return results
