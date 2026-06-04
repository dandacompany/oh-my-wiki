"""Obsidian adapter — obsidian:// URI scheme (no plugin/token needed)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from scripts.viewers.base import VaultRef, Viewer, quote_value

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
