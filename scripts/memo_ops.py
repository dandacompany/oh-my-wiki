"""CRUD operations for individual memo files."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from scripts import frontmatter, registry, reindex, slugify
from scripts.paths import registry_path


def _resolve_slug(root: Path, folder: str, base: str) -> str:
    """Return a non-colliding filename stem under root/folder."""
    folder_dir = root / folder
    candidate = base
    n = 2
    while (folder_dir / f"{candidate}.md").exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def write(
    db_path: Path,
    *,
    vault_id: int,
    title: str,
    body: str,
    folder: str,
    tags: list[str],
    type_: str,
    date_str: str,
    summary: str | None = None,
    status: str | None = "inbox",
) -> str:
    """Create a new memo file. Returns the relpath stored in the registry."""
    root = registry.get_vault_root(db_path, vault_id)
    base = slugify.slugify(title)
    stem = _resolve_slug(root, folder, base)
    relpath = f"{folder}/{stem}.md"

    meta: dict = {
        "title": title,
        "date": date_str,
        "type": type_,
        "tags": list(tags),
    }
    if summary:
        meta["summary"] = summary
    if status:
        meta["status"] = status

    text = frontmatter.dump(meta, body)
    abs_path = root / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(text, encoding="utf-8")

    reindex.incremental(db_path, vault_id=vault_id)
    return relpath


def edit_meta(
    db_path: Path,
    *,
    vault_id: int,
    relpath: str,
    key: str,
    value,
) -> None:
    """Edit a single frontmatter field in place. Body untouched."""
    root = registry.get_vault_root(db_path, vault_id)
    abs_path = root / relpath
    if not abs_path.exists():
        raise FileNotFoundError(relpath)
    text = abs_path.read_text(encoding="utf-8")
    new_text = frontmatter.edit_field(text, key, value)
    abs_path.write_text(new_text, encoding="utf-8")
    reindex.incremental(db_path, vault_id=vault_id)


def move(
    db_path: Path,
    *,
    vault_id: int,
    relpath: str,
    dest_folder: str,
) -> str:
    """Move file to dest_folder, preserve filename. Returns new relpath."""
    root = registry.get_vault_root(db_path, vault_id)
    src = root / relpath
    if not src.exists():
        raise FileNotFoundError(relpath)
    stem = src.stem
    dest_dir = root / dest_folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    new_stem = _resolve_slug(root, dest_folder, stem)
    new_relpath = f"{dest_folder}/{new_stem}.md"
    shutil.move(str(src), str(root / new_relpath))
    registry.delete_note(db_path, vault_id=vault_id, relpath=relpath)
    reindex.incremental(db_path, vault_id=vault_id)
    return new_relpath


def delete(
    db_path: Path,
    *,
    vault_id: int,
    relpath: str,
    hard: bool = False,
) -> str | None:
    """Soft (default) moves to .trash/<ts>-<stem>.md; hard removes file.

    Returns the trash relpath for soft delete, None for hard delete.
    """
    root = registry.get_vault_root(db_path, vault_id)
    src = root / relpath
    if not src.exists():
        raise FileNotFoundError(relpath)
    if hard:
        registry.delete_note(db_path, vault_id=vault_id, relpath=relpath)
        src.unlink()
        return None
    trash_dir = root / ".trash"
    trash_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    trash_relpath = f".trash/{ts}-{src.stem}.md"
    shutil.move(str(src), str(root / trash_relpath))
    registry.delete_note(db_path, vault_id=vault_id, relpath=relpath)
    return trash_relpath


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(prog="scripts.memo_ops")
    sub = p.add_subparsers(dest="cmd", required=True)

    pw = sub.add_parser("write", help="Create a memo (body from stdin)")
    pw.add_argument("--db", default=None)
    pw.add_argument("--vault-id", type=int)
    pw.add_argument("--title", required=True)
    pw.add_argument("--folder", default="inbox")
    pw.add_argument("--tags", default="")
    pw.add_argument("--type", dest="type_", default="note")
    pw.add_argument("--date", dest="date_str", required=True)

    args = p.parse_args(argv)

    db_path = Path(args.db) if args.db else registry_path()
    if args.vault_id is None:
        active = registry.get_active(db_path)
        if active is None:
            print("no active vault — run vault-use first", file=sys.stderr)
            return 2
        vault_id = active["id"]
    else:
        vault_id = args.vault_id

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    body = sys.stdin.read()
    relpath = write(
        db_path,
        vault_id=vault_id,
        title=args.title,
        body=body,
        folder=args.folder,
        tags=tags,
        type_=args.type_,
        date_str=args.date_str,
    )
    print(relpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
