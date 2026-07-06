"""Bulk import external corpora (folder / Obsidian / Notion) into an omw vault.

Deterministic file/API I/O. Default target layer is `raw` (preserve originals);
`--layer wiki` prepends a minimal frontmatter stub to files that lack one.
Idempotent: a file whose dest already exists with identical content is skipped.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

from scripts import net_hints, registry, reindex, slugify

_SKIP_DIRS = {".obsidian", ".git", ".trash"}
_TEXT_EXTS = {".md", ".txt"}
_IMPORT_EXTS = _TEXT_EXTS | {".pdf"}


def _wiki_stub(title: str, *, date: str) -> str:
    return (f"---\ntitle: {title}\ntype: imported\ndate: {date}\ntags: []\n---\n\n")


def _has_frontmatter(text: str) -> bool:
    return text.lstrip().startswith("---")


def import_folder(db_path: Path, *, vault_id: int, src_dir, layer: str = "raw",
                  source: str = "folder") -> dict:
    """Import .md/.txt/.pdf from a folder (or Obsidian vault) into <layer>/import/."""
    src = Path(src_dir)
    root = registry.get_vault_root(db_path, vault_id)
    today = datetime.date.today().isoformat()
    imported, skipped = [], []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _IMPORT_EXTS:
            continue
        rel_to_src = path.relative_to(src).as_posix()
        dest_rel = f"{layer}/import/{rel_to_src}"
        dest = root / dest_rel
        is_text = path.suffix.lower() in _TEXT_EXTS
        if is_text:
            content = path.read_text(encoding="utf-8")
            if layer == "wiki" and not _has_frontmatter(content):
                content = _wiki_stub(path.stem, date=today) + content
            new_bytes = content.encode("utf-8")
        else:
            new_bytes = path.read_bytes()
        if dest.exists() and hashlib.sha256(dest.read_bytes()).digest() == \
                hashlib.sha256(new_bytes).digest():
            skipped.append(dest_rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(new_bytes)
        imported.append(dest_rel)
    reindex.incremental(db_path, vault_id=vault_id)
    return {"imported": imported, "skipped": skipped, "source": source}


class ImportError_(Exception):
    """Import-layer error (named to avoid shadowing builtins.ImportError)."""


_NOTION_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _http_get(url, *, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ImportError_(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ImportError_(f"network error to {url}: {exc}{net_hints.hint_for(exc)}") from exc
    except json.JSONDecodeError as exc:
        raise ImportError_(f"non-JSON response from {url}") from exc


def _http_post(url, *, headers, json_body):
    data = json.dumps(json_body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ImportError_(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ImportError_(f"network error to {url}: {exc}{net_hints.hint_for(exc)}") from exc
    except json.JSONDecodeError as exc:
        raise ImportError_(f"non-JSON response from {url}") from exc


def _rich(rt) -> str:
    return "".join(seg.get("plain_text", "") for seg in (rt or []))


def _blocks_to_markdown(blocks) -> str:
    lines = []
    for b in blocks:
        t = b.get("type")
        data = b.get(t, {}) if t else {}
        txt = _rich(data.get("rich_text"))
        if t == "heading_1":
            lines.append(f"# {txt}")
        elif t == "heading_2":
            lines.append(f"## {txt}")
        elif t == "heading_3":
            lines.append(f"### {txt}")
        elif t == "bulleted_list_item":
            lines.append(f"- {txt}")
        elif t == "numbered_list_item":
            lines.append(f"1. {txt}")
        elif t == "to_do":
            mark = "x" if data.get("checked") else " "
            lines.append(f"- [{mark}] {txt}")
        elif t == "code":
            lines.append(f"```\n{txt}\n```")
        elif t == "quote":
            lines.append(f"> {txt}")
        elif t == "paragraph":
            lines.append(txt)
        # unknown/unsupported block types are skipped
    return "\n\n".join(line for line in lines)


def _notion_headers(token):
    return {"Authorization": f"Bearer {token}", "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json"}


def _notion_page_title(page) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _rich(prop.get("title")) or "untitled"
    return "untitled"


def _notion_children(token, block_id):
    headers = _notion_headers(token)
    out, cursor = [], None
    while True:
        url = f"{_NOTION_BASE}/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        data = _http_get(url, headers=headers)
        out.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break  # defensive: has_more lied or cursor missing — stop
    return out


def import_notion(db_path: Path, *, vault_id: int, token: str, root_id: str,
                  layer: str = "raw") -> dict:
    """Import a Notion page (and its child_page descendants) into <layer>/import/notion/."""
    if not token:
        raise ImportError_("Notion token required — run `omw setup import`")
    root = registry.get_vault_root(db_path, vault_id)
    today = datetime.date.today().isoformat()
    imported = []
    seen: set = set()

    def _import_page(page_id, _depth=0):
        if _depth > 20:
            return  # safety: deep/cyclic page tree
        if page_id in seen:
            return
        seen.add(page_id)
        page = _http_get(f"{_NOTION_BASE}/pages/{page_id}", headers=_notion_headers(token))
        title = _notion_page_title(page)
        blocks = _notion_children(token, page_id)
        body = _blocks_to_markdown(blocks)
        if layer == "wiki":
            body = _wiki_stub(title, date=today) + body
        slug = slugify.slugify(title) or page_id
        dest_rel = f"{layer}/import/notion/{slug}.md"
        dest = root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body + "\n", encoding="utf-8")
        imported.append(dest_rel)
        for b in blocks:
            if b.get("type") == "child_page" and b.get("id"):
                _import_page(b["id"], _depth + 1)
            elif b.get("type") == "child_database" and b.get("id"):
                _import_database(b["id"], _depth + 1)

    def _import_database(db_id, _depth=0):
        if _depth > 20:
            return
        if db_id in seen:
            return
        seen.add(db_id)
        cursor = None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = _http_post(f"{_NOTION_BASE}/databases/{db_id}/query",
                              headers=_notion_headers(token), json_body=body)
            for row in data.get("results", []):
                if row.get("id"):
                    _import_page(row["id"], _depth + 1)   # rows ARE pages
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

    _import_page(root_id)
    reindex.incremental(db_path, vault_id=vault_id)
    return {"imported": imported, "skipped": [], "source": "notion"}
