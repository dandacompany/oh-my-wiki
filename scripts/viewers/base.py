"""Viewer adapter base: VaultRef, Viewer interface, OS launcher, URL encoding."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class VaultRef:
    root: Path
    name: str


def quote_value(value: str) -> str:
    """Percent-encode a URI value (spaces, slashes, non-ASCII)."""
    return quote(value, safe="")


def opener_argv() -> list[str]:
    """The OS command prefix that opens a URI/URL with the default handler."""
    if sys.platform == "darwin":
        return ["open"]
    if sys.platform.startswith("win"):
        return ["cmd", "/c", "start", ""]
    return ["xdg-open"]


def launch(uri: str, *, runner=None) -> str:
    """Open uri with the OS handler. runner is injectable for tests. Returns uri."""
    run = runner or (lambda argv, **kw: subprocess.run(argv, check=False))
    run(opener_argv() + [uri])
    return uri


class Viewer:
    name = "base"
    supports_search = True

    def available(self) -> bool:
        return True

    def open_vault(self, vault: VaultRef) -> str:
        raise NotImplementedError

    def open_page(self, vault: VaultRef, relpath: str) -> str:
        raise NotImplementedError

    def search(self, vault: VaultRef, query: str) -> str:
        raise NotImplementedError

    def scaffold_config(self, vault: VaultRef) -> tuple[list[Path], list[str]]:
        """Write viewer config into the vault. Returns (written_paths, hints)."""
        raise NotImplementedError

    def preflight(self, vault: VaultRef) -> list[str]:
        """Optional checks run just before launching (e.g. app-side registration).
        Returns advisory hint strings; default no-op."""
        return []
