"""Obsidian adapter — obsidian:// URI scheme (no plugin/token needed)."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from scripts.viewers.base import VaultRef, Viewer, quote_value


def app_config_path() -> Path | None:
    """Path to Obsidian's global vault registry (obsidian.json), or None on unknown platforms."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        return Path(base) / "obsidian" / "obsidian.json" if base else None
    return Path.home() / ".config" / "obsidian" / "obsidian.json"


def vault_registered(root: Path, *, config_path: Path | None = None) -> bool:
    """True if `root` is already a registered Obsidian vault."""
    cp = config_path or app_config_path()
    if cp is None or not cp.is_file():
        return False
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    target = str(root)
    return any((v or {}).get("path") == target for v in data.get("vaults", {}).values())


def _register_target(cp, target: str) -> bool:
    """Idempotently add `target` (a path string) to an obsidian.json registry at `cp`."""
    cp = Path(cp)
    try:
        data = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return False
    vaults = data.setdefault("vaults", {})
    if any((v or {}).get("path") == target for v in vaults.values()):
        return False
    vaults[secrets.token_hex(8)] = {"path": target, "ts": int(time.time() * 1000)}
    try:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        return False
    return True


def register_vault(root: Path, *, config_path: Path | None = None) -> bool:
    """Idempotently add `root` to Obsidian's vault registry, preserving existing entries.

    Returns True if a new entry was written; False if already present or unwritable.
    NOTE: a running Obsidian caches its vault list, so a restart (or a one-time
    "Open folder as vault") is needed for a live app to pick up the new entry.
    """
    cp = config_path or app_config_path()
    if cp is None:
        return False
    return _register_target(cp, str(root))


def windows_vault_path(root) -> str:
    """Convert `/mnt/<d>/…` to `D:\…`; else use `platform_env.to_unc_path(root)`."""
    from scripts import platform_env
    s = str(root)
    m = re.match(r"^/mnt/([a-z])/(.*)$", s)
    if m:
        return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
    return platform_env.to_unc_path(root)


def windows_obsidian_config() -> Path | None:
    """Windows-side obsidian.json: `<win profile>/AppData/Roaming/obsidian/obsidian.json`."""
    from scripts import platform_env
    wp = platform_env.windows_user_profile()
    return (wp / "AppData" / "Roaming" / "obsidian" / "obsidian.json") if wp else None


def register_vault_windows(root, *, config_path=None) -> bool:
    """Idempotently add Windows-side vault path to obsidian.json."""
    cp = config_path or windows_obsidian_config()
    if cp is None:
        return False
    return _register_target(cp, windows_vault_path(root))


def obsidian_installed() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/Obsidian.app").exists() or shutil.which("obsidian") is not None
    if sys.platform.startswith("win"):
        return shutil.which("obsidian") is not None
    # linux / wsl
    if shutil.which("obsidian") is not None:
        return True
    return any(Path(p).exists() for p in (
        "/usr/bin/obsidian", "/usr/local/bin/obsidian", "/opt/Obsidian/obsidian"))


_CORE_PLUGINS = [
    "file-explorer", "switcher", "command-palette", "outline", "bookmarks",
    "graph", "backlink", "outgoing-link", "page-preview",
    "global-search", "properties", "tag-pane",
]
_APP_SETTINGS = {"alwaysUpdateLinks": True, "useMarkdownLinks": False}


class ObsidianViewer(Viewer):
    name = "obsidian"
    supports_search = True

    def available(self) -> bool:
        if sys.platform == "darwin":
            return Path("/Applications/Obsidian.app").exists() or shutil.which("obsidian") is not None
        return shutil.which("obsidian") is not None or True  # best-effort; URI may still work

    def open_vault(self, vault: VaultRef) -> str:
        return f"obsidian://open?vault={quote_value(vault.name)}"

    def open_page(self, vault: VaultRef, relpath: str) -> str:
        abs_path = str((vault.root / relpath))
        return f"obsidian://open?path={quote_value(abs_path)}"

    def search(self, vault: VaultRef, query: str) -> str:
        return f"obsidian://search?vault={quote_value(vault.name)}&query={quote_value(query)}"

    def preflight(self, vault: VaultRef) -> list[str]:
        """Before launching: ensure the vault is in Obsidian's registry, else the
        obsidian:// URI fails with "Vault not found". Auto-registers + advises."""
        if vault_registered(vault.root):
            return []
        added = register_vault(vault.root)
        hints = ["이 볼트가 Obsidian에 등록돼 있지 않아 obsidian:// 링크가 바로 열리지 않을 수 있습니다."]
        if added:
            hints.append("  → obsidian.json에 등록했습니다. Obsidian이 실행 중이면 한 번 재시작하세요.")
        hints.append(f"  → 또는 Obsidian에서 'Open folder as vault'로 이 폴더를 한 번 열어주세요: {vault.root}")
        return hints

    def scaffold_config(self, vault: VaultRef) -> tuple[list[Path], list[str]]:
        cfg = vault.root / ".obsidian"
        cfg.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []

        cp = cfg / "core-plugins.json"
        existing = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else []
        merged = list(dict.fromkeys(list(existing) + _CORE_PLUGINS))  # union, order-stable
        cp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        written.append(cp)

        app = cfg / "app.json"
        app_data = json.loads(app.read_text(encoding="utf-8")) if app.is_file() else {}
        app_data.update(_APP_SETTINGS)
        app.write_text(json.dumps(app_data, indent=2), encoding="utf-8")
        written.append(app)

        hints = []
        if register_vault(vault.root):
            hints.append("Obsidian 볼트 레지스트리에 등록했습니다. Obsidian이 실행 중이면 재시작 후 "
                         "`omw view`가 바로 열립니다(미실행 시 다음 실행부터 자동 인식).")
        dv = cfg / "plugins" / "dataview"
        if dv.is_dir():
            comm = cfg / "community-plugins.json"
            cur = json.loads(comm.read_text(encoding="utf-8")) if comm.is_file() else []
            if "dataview" not in cur:
                cur.append("dataview")
                comm.write_text(json.dumps(cur, indent=2), encoding="utf-8")
                written.append(comm)
        else:
            hints.append("Dataview(인라인 필드 표)는 커뮤니티 플러그인입니다. "
                         "Obsidian에서 설치 후 다시 실행하면 community-plugins.json에 추가됩니다.")
        return written, hints


_MANUAL = "https://obsidian.md/download 에서 설치하세요."


def _confirm(assume_yes: bool, interactive: bool) -> bool:
    if assume_yes:
        return True
    if not interactive:
        return False
    try:
        ans = input("Obsidian이 설치돼 있지 않습니다. 지금 설치할까요? [y/N] ")
    except EOFError:
        return False
    return ans.strip().lower().startswith("y")


def _is_debian_like() -> bool:
    return shutil.which("apt") is not None or shutil.which("apt-get") is not None


def _latest_deb_url() -> str:
    api = "https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest"
    with urllib.request.urlopen(api, timeout=15) as r:  # noqa: S310 (trusted host)
        data = json.loads(r.read().decode("utf-8"))
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith("_amd64.deb"):
            return asset["browser_download_url"]
    raise RuntimeError("no amd64 .deb asset found in latest release")


def _download(url: str, dest) -> None:
    with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:  # noqa: S310
        shutil.copyfileobj(r, f)


def _install_deb() -> tuple[bool, str]:
    try:
        url = _latest_deb_url()
        dest = Path(tempfile.gettempdir()) / "obsidian.deb"
        _download(url, dest)
        subprocess.run(["sudo", "apt", "install", "-y", str(dest)], check=True)
    except Exception as e:  # network/apt/sudo failure → manual fallback
        return False, f".deb 설치 실패 ({e}). {_MANUAL}"
    return True, "Obsidian(.deb) 설치 완료. WSL이면 `obsidian`으로 WSLg에서 실행하세요."


def install_obsidian(*, assume_yes: bool = False, interactive: bool = True) -> tuple[bool, str]:
    if obsidian_installed():
        return True, "Obsidian이 이미 설치돼 있습니다."
    if not _confirm(assume_yes, interactive):
        return False, f"설치를 건너뜁니다. 직접 설치: {_MANUAL}"
    if sys.platform == "darwin":
        if shutil.which("brew"):
            try:
                subprocess.run(["brew", "install", "--cask", "obsidian"], check=True)
            except Exception as e:
                return False, f"brew 설치 실패 ({e}). {_MANUAL}"
            return True, "Obsidian 설치 완료(brew cask)."
        return False, f"brew가 없습니다. {_MANUAL}"
    if _is_debian_like():
        return _install_deb()
    return False, f"자동 설치를 지원하지 않는 플랫폼입니다. {_MANUAL}"
