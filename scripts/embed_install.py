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


def sqlite_vec_available() -> bool:
    from scripts import vector_index
    return vector_index.available()


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


def ensure_sqlite_vec(*, assume_yes: bool = False, interactive: bool = True) -> bool:
    """Ensure the vector-store extension is importable."""
    if sqlite_vec_available():
        return True
    if not assume_yes:
        if not (interactive and sys.stdin.isatty()):
            return False
        try:
            ans = input("sqlite-vec (local vector store) is not installed. Install now? [y/N] ")
        except EOFError:
            return False
        if not ans.strip().lower().startswith("y"):
            return False
    try:
        subprocess.run(platform_env.pip_install_argv("sqlite-vec"), check=True)
    except Exception:
        return False
    return sqlite_vec_available()


def ensure_local_embedding(*, assume_yes: bool = False, interactive: bool = True) -> bool:
    """Install the complete local retrieval path, not only the model runner."""
    if fastembed_available() and sqlite_vec_available():
        return True
    if not assume_yes:
        if not (interactive and sys.stdin.isatty()):
            return False
        try:
            ans = input("fastembed + sqlite-vec are required. Install both now? [y/N] ")
        except EOFError:
            return False
        if not ans.strip().lower().startswith("y"):
            return False
    return (
        ensure_fastembed(assume_yes=True, interactive=False)
        and ensure_sqlite_vec(assume_yes=True, interactive=False)
    )
