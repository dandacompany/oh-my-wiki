"""Mode-neutral page removal with recoverable trash and backlink cleanup."""
from __future__ import annotations

import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from scripts import frontmatter, links, registry, reindex
from scripts import relations as relations_mod
from scripts.paths import ensure_vault_trash, vault_trash_root

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_INLINE_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s+)?([A-Za-z][\w \-]*?)\s*::\s*(.+?)\s*$"
)


def _slug(target: str) -> str:
    target = target.strip()
    if target.startswith("[[") and target.endswith("]]"):
        target = target[2:-2]
    value = target.split("|", 1)[0].split("#", 1)[0].split("?", 1)[0]
    value = value.strip().split("/")[-1]
    return value[:-3].lower() if value.lower().endswith(".md") else value.lower()


def _rewrite_body(body: str, target_slugs: set[str]) -> str:
    def wikilink(match: re.Match) -> str:
        raw = match.group(1)
        if _slug(raw) not in target_slugs:
            return match.group(0)
        return raw.split("|", 1)[1] if "|" in raw else raw.split("#", 1)[0].split("/")[-1]

    def mdlink(match: re.Match) -> str:
        target = match.group(2).strip()
        if target.lower().startswith(("http://", "https://", "mailto:")):
            return match.group(0)
        return match.group(1) if _slug(target) in target_slugs else match.group(0)

    rewritten = _WIKILINK_RE.sub(wikilink, body)
    rewritten = _MDLINK_RE.sub(mdlink, rewritten)
    lines = []
    for line in rewritten.splitlines(keepends=True):
        field = _INLINE_FIELD_RE.match(line.rstrip("\r\n"))
        if (field and field.group(1).strip().lower() in links._RELATIONS
                and _slug(field.group(2)) in target_slugs):
            continue
        lines.append(line)
    return "".join(lines)


def relation_targets(meta: dict) -> dict:
    """This page's relations as {verb: [target, ...]}, whichever shape it was written in."""
    return relations_mod.normalize((meta or {}).get("relations"))


def _rewrite_source(path: Path, target_slugs: set[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    had_frontmatter = text.startswith("---\n")
    meta, body = frontmatter.parse(text)
    changed_meta = False
    # Normalize first: list-shaped relations used to fall through this block entirely,
    # so deleting a page left dangling references behind in those files. A page that is
    # rewritten here is written back in the canonical mapping shape.
    normalized = relations_mod.normalize(meta.get("relations"))
    if normalized:
        kept_all = {}
        for key, values in normalized.items():
            kept = [item for item in values if _slug(str(item)) not in target_slugs]
            if len(kept) != len(values):
                changed_meta = True
            if kept:
                kept_all[key] = kept
        if changed_meta:
            if kept_all:
                meta["relations"] = kept_all
            else:
                meta.pop("relations", None)
    new_body = _rewrite_body(body, target_slugs)
    if not changed_meta and new_body == body:
        return False
    new_text = frontmatter.dump(meta, new_body) if had_frontmatter else new_body
    path.write_text(new_text, encoding="utf-8")
    return True


def delete(
    db_path: Path, *, vault_id: int, relpath: str, hard: bool = False,
    rewrite_backlinks: bool = True,
) -> dict:
    """Delete a memo or wiki page; soft delete is always the default."""
    vault = registry.get_vault_by_id(db_path, vault_id)
    if vault is None:
        raise registry.VaultError(f"vault id {vault_id} not found")
    root = Path(vault["path"])
    src = root / relpath
    if not src.is_file():
        raise FileNotFoundError(relpath)

    inbound = links.backlinks(db_path, vault_id, relpath) if rewrite_backlinks else []
    by_source: dict[str, set[str]] = defaultdict(set)
    for row in inbound:
        by_source[row["relpath"]].add(row["dst_slug"])

    trash_value = None
    if hard:
        src.unlink()
    else:
        trash = vault_trash_root(root, vault["name"], vault["config_json"])
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except OSError:
            trash = ensure_vault_trash(root, vault["name"])
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        dest = trash / f"{ts}-{src.name}"
        shutil.move(str(src), str(dest))
        try:
            trash_value = str(dest.relative_to(root))
        except ValueError:
            trash_value = str(dest)

    rewritten, skipped = [], []
    for source_relpath, slugs in sorted(by_source.items()):
        source = root / source_relpath
        try:
            if source.is_file() and _rewrite_source(source, slugs):
                rewritten.append(source_relpath)
        except (OSError, UnicodeError, frontmatter.FrontmatterError):
            skipped.append(source_relpath)

    registry.delete_note(db_path, vault_id=vault_id, relpath=relpath)
    reindex.incremental(db_path, vault_id=vault_id)
    return {"deleted": relpath, "hard": hard, "trash": trash_value,
            "backlinks_rewritten": rewritten, "backlinks_skipped": skipped}
