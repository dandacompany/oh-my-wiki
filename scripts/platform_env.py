"""Pure environment probes for WSL / Windows-interop awareness. No side effects."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_WIN_USERS = Path("/mnt/c/Users")
_SKIP_USERS = {"Public", "Default", "Default User", "All Users", "desktop.ini"}


def _proc_version() -> str:
    try:
        return Path("/proc/version").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    return "microsoft" in _proc_version().lower()


def wsl_distro() -> str | None:
    return os.environ.get("WSL_DISTRO_NAME") or None


def _userprofile_windows() -> str | None:
    """%USERPROFILE% via cmd.exe interop, e.g. 'C:\\Users\\dante'. None on failure."""
    try:
        out = subprocess.run(["cmd.exe", "/c", "echo", "%USERPROFILE%"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    s = (out.stdout or "").strip()
    return s if s and "%" not in s else None


def _win_to_wsl(winpath: str) -> Path | None:
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", winpath.strip())
    if not m:
        return None
    return Path(f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}")


def windows_user_profile() -> Path | None:
    wp = _userprofile_windows()
    if wp:
        p = _win_to_wsl(wp)
        if p is not None:
            return p
    if _WIN_USERS.is_dir():
        for d in sorted(_WIN_USERS.iterdir()):
            if d.is_dir() and d.name not in _SKIP_USERS:
                return d
    return None


def to_unc_path(linux_path, distro: str | None = None) -> str:
    distro = distro or wsl_distro() or "Ubuntu"
    p = str(linux_path).replace("/", "\\")
    return f"\\\\wsl.localhost\\{distro}{p}"
