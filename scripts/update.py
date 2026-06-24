"""omw self-update: env-aware upgrade + PyPI version check + managed-block refresh.
Best-effort and non-blocking — never raises to the shell. Touches only the package
install + host instruction blocks; never the vault registry or knowledge content."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request

from scripts import banner, platform_env

_PYPI = "https://pypi.org/pypi/{pkg}/json"


def latest_version(pkg: str, *, timeout: int = 5) -> str | None:
    try:
        with urllib.request.urlopen(_PYPI.format(pkg=pkg), timeout=timeout) as r:
            return (json.loads(r.read()).get("info") or {}).get("version")
    except Exception:
        return None


def _refresh_blocks(base_dir=None) -> None:
    from scripts import setup_wizard
    try:
        setup_wizard.setup_recall(noninteractive=True, base_dir=base_dir)
    except Exception:
        pass
    try:
        setup_wizard.setup_agents(noninteractive=True)
    except Exception:
        pass


def _confirm(msg: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(f"{msg} [y/N] ").strip().lower().startswith("y")
    except EOFError:
        return False


def run(*, check_only: bool, assume_yes: bool, refresh: bool, base_dir=None) -> int:
    import os
    cur = banner.version()
    latest = latest_version("oh-my-wiki")
    if latest is None:
        print(f"omw {cur} (latest version unknown — network?)")
    elif latest == cur:
        print(f"omw {cur} is up to date.")
        return 0   # already current — never re-run the upgrade command (even with --yes)
    else:
        print(f"omw {cur} → {latest} available")
    if check_only:
        return 0
    assume_yes = assume_yes or os.environ.get("OMW_UPDATE_YES") == "1"
    if not assume_yes and not _confirm("Upgrade omw now?"):
        print("update skipped.")
        return 0
    argv = platform_env.upgrade_argv("oh-my-wiki")
    print("running:", " ".join(argv))
    cp = subprocess.run(argv)
    if cp.returncode != 0:
        print(f"error: upgrade command failed (rc={cp.returncode}).", file=sys.stderr)
        return cp.returncode
    if refresh and (assume_yes or _confirm("Regenerate managed host blocks for the new version?")):
        _refresh_blocks(base_dir)
        print("managed blocks regenerated (config preserved).")
    print("updated. Restart your agent session to load the new version.")
    return 0
