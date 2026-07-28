"""Vault storage adapters. v1 supports markdown and obsidian."""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Protocol

from scripts.paths import ensure_vault_trash


class AdapterError(Exception):
    pass


# Ordered, user-facing contract shared by every vault entry point.
VAULT_MODES = (
    "wiki",
    "memo",
    "personal",
    "book",
    "business",
    "github-codebase",
    "website",
)


class VaultAdapter(Protocol):
    def open(self, abs_path: Path) -> None: ...
    def link_syntax(self, target_relpath: str) -> str: ...
    def init_vault(self, root: Path, mode: str) -> Path: ...
    def is_valid(self, root: Path) -> bool: ...


def _os_open(target: Path) -> None:
    """Cross-platform 'open this file with the default app'."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(target)], check=False)
    elif system == "Windows":
        subprocess.run(["cmd", "/c", "start", "", str(target)], check=False, shell=False)
    else:
        subprocess.run(["xdg-open", str(target)], check=False)


_INDEX_TEMPLATE = """---
title: Wiki Index
type: meta
status: meta
---

## Concepts

## Entities

## Summaries
"""

_LOG_TEMPLATE = "# Operation Log\n"

_PERSONAL_INDEX_TEMPLATE = """---
title: Personal Index
type: meta
status: meta
---

## Journal

## Goals

## People

## Health
"""

_BOOK_INDEX_TEMPLATE = """---
title: Book Index
type: meta
status: meta
---

## Chapters

## Characters

## Worldbuilding

## Outlines

## Drafts
"""

_BUSINESS_INDEX_TEMPLATE = """---
title: Business Index
type: meta
status: meta
---

## Meetings

## Decisions

## Clients

## Vendors

## Processes
"""

_GITHUB_CODEBASE_INDEX_TEMPLATE = """---
title: Codebase Index
type: meta
status: meta
---

## Modules

## APIs

## Decisions

## Runbooks

## Glossary
"""

_WEBSITE_INDEX_TEMPLATE = """---
title: Website Index
type: meta
status: meta
---

## Pages

## Posts

## Assets

## SEO

## Outlines
"""


class MarkdownAdapter:
    """Plain-markdown adapter — works with any editor (VS Code, Cursor, etc.)."""

    def __init__(self, *, vault_name: str | None = None):
        self.vault_name = vault_name

    def open(self, abs_path: Path) -> None:
        _os_open(abs_path)

    def link_syntax(self, target_relpath: str) -> str:
        rel = target_relpath
        if rel.endswith(".md"):
            rel = rel[:-3]
        name = rel.rsplit("/", 1)[-1]
        return f"[{name}](./{rel}.md)"

    def init_vault(self, root: Path, mode: str) -> Path:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        trash = ensure_vault_trash(root, self.vault_name or root.name)
        if mode == "memo":
            self._init_memo(root)
        elif mode == "wiki":
            self._init_wiki(root)
        elif mode == "personal":
            self._init_personal(root)
        elif mode == "book":
            self._init_book(root)
        elif mode == "business":
            self._init_business(root)
        elif mode == "github-codebase":
            self._init_github_codebase(root)
        elif mode == "website":
            self._init_website(root)
        else:
            raise AdapterError(f"unknown mode: {mode!r}")
        return trash

    def _init_memo(self, root: Path) -> None:
        (root / "inbox").mkdir(exist_ok=True)

    def _init_wiki(self, root: Path) -> None:
        (root / "raw").mkdir(exist_ok=True)
        wiki = root / "wiki"
        wiki.mkdir(exist_ok=True)
        for sub in ("summaries", "entities", "concepts", "comparisons", "syntheses"):
            (wiki / sub).mkdir(exist_ok=True)
        index_path = wiki / "index.md"
        log_path = wiki / "log.md"
        if not index_path.exists():
            index_path.write_text(_INDEX_TEMPLATE, encoding="utf-8")
        if not log_path.exists():
            log_path.write_text(_LOG_TEMPLATE, encoding="utf-8")

    def _init_personal(self, root: Path) -> None:
        for sub in ("journal", "goals", "people", "health"):
            (root / sub).mkdir(exist_ok=True)
        index_path = root / "index.md"
        if not index_path.exists():
            index_path.write_text(_PERSONAL_INDEX_TEMPLATE, encoding="utf-8")

    def _init_book(self, root: Path) -> None:
        for sub in ("chapters", "characters", "worldbuilding", "outlines", "drafts"):
            (root / sub).mkdir(exist_ok=True)
        index_path = root / "index.md"
        if not index_path.exists():
            index_path.write_text(_BOOK_INDEX_TEMPLATE, encoding="utf-8")

    def _init_business(self, root: Path) -> None:
        for sub in ("meetings", "decisions", "clients", "vendors", "processes"):
            (root / sub).mkdir(exist_ok=True)
        index_path = root / "index.md"
        if not index_path.exists():
            index_path.write_text(_BUSINESS_INDEX_TEMPLATE, encoding="utf-8")

    def _init_github_codebase(self, root: Path) -> None:
        for sub in ("modules", "apis", "decisions", "runbooks", "glossary"):
            (root / sub).mkdir(exist_ok=True)
        index_path = root / "index.md"
        if not index_path.exists():
            index_path.write_text(_GITHUB_CODEBASE_INDEX_TEMPLATE, encoding="utf-8")

    def _init_website(self, root: Path) -> None:
        for sub in ("pages", "posts", "assets", "seo", "outlines"):
            (root / sub).mkdir(exist_ok=True)
        index_path = root / "index.md"
        if not index_path.exists():
            index_path.write_text(_WEBSITE_INDEX_TEMPLATE, encoding="utf-8")

    def is_valid(self, root: Path) -> bool:
        return Path(root).is_dir()


def get_adapter(type_: str, *, vault_name: str | None = None) -> VaultAdapter:
    if type_ == "markdown":
        return MarkdownAdapter(vault_name=vault_name)
    if type_ == "obsidian":
        return ObsidianAdapter(vault_name=vault_name)
    raise AdapterError(f"unknown adapter type: {type_!r}")


class ObsidianAdapter(MarkdownAdapter):
    """Obsidian-aware adapter. Uses obsidian:// URI scheme to open notes."""

    def __init__(self, vault_name: str | None = None) -> None:
        self.vault_name = vault_name

    def link_syntax(self, target_relpath: str) -> str:
        rel = target_relpath
        if rel.endswith(".md"):
            rel = rel[:-3]
        return f"[[{rel}]]"

    def is_valid(self, root: Path) -> bool:
        root = Path(root)
        return root.is_dir() and (root / ".obsidian").is_dir()

    def init_vault(self, root: Path, mode: str) -> Path:
        trash = super().init_vault(root, mode)
        (Path(root) / ".obsidian").mkdir(exist_ok=True)
        return trash

    def open(self, abs_path: Path, vault_root: Path | None = None) -> None:
        if self.vault_name and vault_root is not None:
            try:
                rel = Path(abs_path).resolve().relative_to(Path(vault_root).resolve())
            except ValueError:
                rel = Path(abs_path).name
            from urllib.parse import quote
            uri = f"obsidian://open?vault={quote(self.vault_name)}&file={quote(str(rel), safe='/')}"
            _os_open_uri(uri)
            return
        _os_open(abs_path)


def _os_open_uri(uri: str) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", uri], check=False)
    elif system == "Windows":
        subprocess.run(["cmd", "/c", "start", "", uri], check=False, shell=False)
    else:
        subprocess.run(["xdg-open", uri], check=False)
