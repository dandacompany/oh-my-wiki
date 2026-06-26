"""scripts/uninstall.py — safe teardown of omw's host integration.

The inverse of `omw setup`: detect (read-only `plan`) then remove (tier-gated
`apply`) the managed marker blocks, native hooks, and skill bundle omw installed.
Never deletes user knowledge (vaults/registry) without an explicit flag.
stdlib only; `plan()` never raises.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import persona_export, recall, commandmap

#: The four managed marker names, sourced from their owning modules (SSOT).
MARKERS: tuple[str, ...] = (
    persona_export.MARKER,        # "omw-personas"
    recall.MARKER,                # "omw-recall"
    recall.ALWAYS_ON_MARKER,      # "omw-wiki-first"
    commandmap.MARKER,            # "omw-commandmap"
)


def strip_marker_block(text: str, marker: str) -> tuple[str, bool]:
    """Remove the inclusive `<!-- {marker}:start -->`…`<!-- {marker}:end -->` region.

    Preserves everything outside the fences; collapses the seam to at most one
    blank line; ensures a single trailing newline when the result is non-empty.
    Returns (new_text, removed). No-op (text, False) if a fence is missing.
    """
    start = f"<!-- {marker}:start -->"
    end = f"<!-- {marker}:end -->"
    i = text.find(start)
    j = text.find(end)
    if i == -1 or j == -1 or j < i:
        return text, False
    pre = text[:i].rstrip("\n")
    post = text[j + len(end):].lstrip("\n")
    if pre and post:
        new = pre + "\n\n" + post
    else:
        new = pre + post
    if new and not new.endswith("\n"):
        new += "\n"
    return new, True


def _is_omw_recall_cmd(cmd: str) -> bool:
    """Mirror recall._event_has_recall: an omw recall hook invocation."""
    return "recall" in cmd and ("preamble" in cmd or "prompt" in cmd or "pretool" in cmd)


def _strip_omw_hooks(config_path) -> tuple[int, bool]:
    """Remove only omw-recall hook groups from one host hook JSON. Returns
    (removed_count, changed). Best-effort; never raises."""
    path = Path(config_path)
    if not path.exists():
        return 0, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0, False
    if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
        return 0, False
    hooks = data["hooks"]
    removed = 0
    for event in list(hooks.keys()):
        groups = hooks.get(event) or []
        kept = []
        for group in groups:
            inner = (group or {}).get("hooks", []) if isinstance(group, dict) else []
            if any(_is_omw_recall_cmd((h if isinstance(h, dict) else {}).get("command", "")) for h in inner):
                removed += 1
            else:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del data["hooks"]
    if removed:
        try:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        except OSError:
            return 0, False
    return removed, removed > 0


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _detect_host_markers(base, host, *, profile, workspace) -> dict | None:
    from scripts import hosts as hostsmod
    try:
        path = hostsmod.resolve_instruction_path(host, base, profile=profile, workspace=workspace)
    except Exception:
        return None
    if not path.exists():
        return None
    text = _safe(lambda: path.read_text(encoding="utf-8"), "")
    present = [m for m in MARKERS if f"<!-- {m}:start -->" in text]
    if not present:
        return None
    return {"host": host, "path": str(path), "markers": present}


def _detect_hooks() -> list:
    out = []
    for host, path in recall.host_hook_configs().items():
        if not path.exists():
            continue
        data = _safe(lambda: json.loads(path.read_text(encoding="utf-8")), None)
        if not isinstance(data, dict) or not isinstance(data.get("hooks"), dict):
            continue
        count = 0
        for groups in data["hooks"].values():
            for group in groups or []:
                inner = (group or {}).get("hooks", []) if isinstance(group, dict) else []
                if any(_is_omw_recall_cmd((h if isinstance(h, dict) else {}).get("command", "")) for h in inner):
                    count += 1
        if count:
            out.append({"host": host, "path": str(path), "count": count})
    return out


def _detect_skills() -> list:
    from scripts import agent_skills
    out = []
    for agent, skills_dir in agent_skills._SKILLS_DIR.items():
        bundle = Path(skills_dir) / "oh-my-wiki"
        if bundle.exists():
            out.append({"agent": agent, "path": str(bundle)})
    # hermes per-profile targets (beyond the main ~/.hermes/skills already covered above)
    for t in _safe(agent_skills.hermes_profile_targets, []):
        bundle = Path(t["skills_dir"]) / "oh-my-wiki"
        if bundle.exists() and not any(s["path"] == str(bundle) for s in out):
            out.append({"agent": f"hermes:{t['name']}", "path": str(bundle)})
    return out


def _detect_home() -> dict:
    from scripts import paths, registry
    home = paths.omw_home()
    reg = paths.registry_path()
    vaults = []
    if reg.exists():
        for v in _safe(lambda: registry.list_vaults(reg, include_archived=True), []):
            vaults.append({"name": v["name"], "path": v["path"]})
    config_present = any((home / n).exists() for n in ("config.yaml", "config.yml", "config.json"))
    return {
        "path": str(home), "exists": home.exists(),
        "config": config_present, "env": (home / ".env").exists(),
        "registry": reg.exists(), "vaults": vaults,
    }


def _pip_hint() -> str:
    import sys
    # pipx installs live under a pipx venvs path; otherwise plain pip.
    if "pipx" in sys.prefix or "/pipx/" in sys.executable:
        return "pipx uninstall oh-my-wiki"
    return "pip uninstall oh-my-wiki"


def plan(base_dir, *, hosts=None, profile=None, workspace=None) -> dict:
    """Read-only detection of every surface omw installed. Never raises."""
    from scripts import hosts as hostsmod
    base = Path(base_dir) if base_dir else Path.cwd()
    host_names = hosts if hosts else list(hostsmod.HOSTS.keys())
    host_hits = []
    for h in host_names:
        hit = _safe(lambda h=h: _detect_host_markers(base, h, profile=profile, workspace=workspace), None)
        if hit:
            host_hits.append(hit)
    return {
        "hosts": host_hits,
        "hooks": _safe(_detect_hooks, []),
        "skills": _safe(_detect_skills, []),
        "home": _safe(_detect_home, {"path": "", "exists": False, "config": False,
                                     "env": False, "registry": False, "vaults": []}),
        "pip_hint": _safe(_pip_hint, "pip uninstall oh-my-wiki"),
    }
