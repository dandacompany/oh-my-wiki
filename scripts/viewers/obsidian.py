"""Obsidian adapter — obsidian:// URI scheme (no plugin/token needed)."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import time
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


def register_vault(root: Path, *, config_path: Path | None = None) -> bool:
    """Idempotently add `root` to Obsidian's vault registry, preserving existing entries.

    Returns True if a new entry was written; False if already present or unwritable.
    NOTE: a running Obsidian caches its vault list, so a restart (or a one-time
    "Open folder as vault") is needed for a live app to pick up the new entry.
    """
    cp = config_path or app_config_path()
    if cp is None:
        return False
    target = str(root)
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
