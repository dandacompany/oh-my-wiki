"""Pure environment probes for WSL / Windows-interop awareness. No side effects."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import sysconfig
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
    try:
        if _WIN_USERS.is_dir():
            for d in sorted(_WIN_USERS.iterdir()):
                if d.is_dir() and d.name not in _SKIP_USERS:
                    return d
    except OSError:
        return None
    return None


def to_unc_path(linux_path, distro: str | None = None) -> str:
    distro = distro or wsl_distro() or "Ubuntu"
    p = str(linux_path).replace("/", "\\")
    return f"\\\\wsl.localhost\\{distro}{p}"


def _prefix() -> str:
    return sys.prefix


def _base_prefix() -> str:
    return sys.base_prefix


def _executable() -> str:
    return sys.executable


def omw_install_context() -> str:
    """How omw's interpreter is installed: 'pipx' | 'venv' | 'system'."""
    prefix = _prefix()
    if "pipx" in prefix and "venvs" in prefix:   # ~/.local/share/pipx/venvs/oh-my-wiki
        return "pipx"
    if _prefix() != _base_prefix():
        return "venv"
    return "system"


def pep668_managed() -> bool:
    """True if the active stdlib is PEP 668 externally-managed (Debian/Ubuntu)."""
    try:
        return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists()
    except (OSError, KeyError):
        return False


def pip_install_argv(pkg: str) -> list[str]:
    """The correct install command for `pkg` into omw's own environment."""
    ctx = omw_install_context()
    if ctx == "pipx":
        return ["pipx", "inject", "oh-my-wiki", pkg, "--include-apps"]
    if ctx == "venv":
        return [_executable(), "-m", "pip", "install", pkg]
    if pep668_managed():
        return [_executable(), "-m", "pip", "install", "--break-system-packages", pkg]
    return [_executable(), "-m", "pip", "install", pkg]
