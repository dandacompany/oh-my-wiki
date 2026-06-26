"""On-demand installer for the optional fastembed local embedder. Mirrors
setup_wizard.ensure_wizard_ui: best-effort, never raises to the caller."""
from __future__ import annotations

import subprocess
import sys

from scripts import platform_env


def fastembed_available() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except Exception:
        return False


def ensure_fastembed(*, assume_yes: bool = False, interactive: bool = True) -> bool:
    """Ensure fastembed is importable; install it on demand. Returns availability."""
    if fastembed_available():
        return True
    if not assume_yes:
        if not (interactive and sys.stdin.isatty()):
            return False
        try:
            ans = input("fastembed (local embedding) is not installed. Install now? [y/N] ")
        except EOFError:
            return False
        if not ans.strip().lower().startswith("y"):
            return False
    try:
        subprocess.run(platform_env.pip_install_argv("fastembed"), check=True)
    except Exception:
        return False
    return fastembed_available()
