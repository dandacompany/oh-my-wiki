"""On-demand installer for the optional kiwipiepy Korean analyzer. Mirrors
embed_install: best-effort, never raises to the caller."""
from __future__ import annotations

import subprocess
import sys

from scripts import platform_env


def kiwi_available() -> bool:
    try:
        import kiwipiepy  # noqa: F401
        return True
    except Exception:
        return False


def ensure_kiwi(*, assume_yes: bool = False, interactive: bool = True) -> bool:
    """Ensure kiwipiepy is importable; install it on demand. Returns availability."""
    if kiwi_available():
        return True
    if not assume_yes:
        if not (interactive and sys.stdin.isatty()):
            return False
        try:
            ans = input("kiwipiepy (Korean morphological analyzer) is not installed. Install now? [y/N] ")
        except EOFError:
            return False
        if not ans.strip().lower().startswith("y"):
            return False
    try:
        subprocess.run(platform_env.pip_install_argv("kiwipiepy"), check=True)
    except Exception:
        return False
    return kiwi_available()
