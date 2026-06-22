"""Register a memo folder as a memo-mode vault, with optional frontmatter migration."""
from __future__ import annotations

import shutil
from datetime import date as _date, datetime
from pathlib import Path

from scripts import frontmatter, reindex, registry

DEFAULT_TYPE = "note"


def _scan_files(root: Path) -> list[Path]:
    return [p for p in sorted(root.rglob("*.md")) if ".trash" not in p.parts]


def _plan_changes(meta: dict, today: str) -> list[dict]:
    """Return ordered list of changes to bring meta in line with oh-my-wiki rules."""
    changes: list[dict] = []
    if "title" not in meta:
        changes.append({"field": "title", "op": "add", "value": "Untitled"})
    if "date" not in meta:
        changes.append({"field": "date", "op": "add", "value": today})
    if "type" not in meta:
        changes.append({"field": "type", "op": "add", "value": DEFAULT_TYPE})
    if "tags" not in meta:
        changes.append({"field": "tags", "op": "add", "value": []})
    elif not isinstance(meta["tags"], list):
        if isinstance(meta["tags"], str):
            new = [t.strip() for t in meta["tags"].split(",") if t.strip()]
        else:
            new = [str(meta["tags"])]
        changes.append({"field": "tags", "op": "normalize", "value": new})
    return changes


def dry_run(db_path: Path, *, vault_id: int) -> dict:
    """Return a per-file plan without mutating anything."""
    root = registry.get_vault_root(db_path, vault_id)

    today = _date.today().isoformat()
    files: list[dict] = []
    needs = 0
    clean = 0
    for f in _scan_files(root):
        relpath = str(f.relative_to(root))
        text = f.read_text(encoding="utf-8")
        try:
            meta, _ = frontmatter.parse(text)
        except frontmatter.FrontmatterError as exc:
            files.append({
                "relpath": relpath,
                "changes": [{"field": "_yaml_", "op": "skip", "value": str(exc)}],
            })
            needs += 1
            continue
        changes = _plan_changes(meta, today)
        files.append({"relpath": relpath, "changes": changes})
        if changes:
            needs += 1
        else:
            clean += 1

    return {
        "vault_id": vault_id,
        "vault_path": str(root),
        "files": files,
        "summary": {
            "total": len(files),
            "needs_changes": needs,
            "clean": clean,
        },
    }


def apply(db_path: Path, *, vault_id: int, plan: dict) -> dict:
    """Mutate files per plan. Backs up the pre-image of each changed file to .trash/."""
    root = registry.get_vault_root(db_path, vault_id)
    trash = root / ".trash"
    trash.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    applied = 0
    skipped = 0
    for entry in plan["files"]:
        changes = entry["changes"]
        if not changes:
            continue
        # Skip files we couldn't even parse
        if any(c["op"] == "skip" for c in changes):
            skipped += 1
            continue
        relpath = entry["relpath"]
        abs_path = root / relpath
        original = abs_path.read_text(encoding="utf-8")

        # Backup pre-image
        safe_name = relpath.replace("/", "__")
        backup = trash / f"{ts}-pre-import-{safe_name}"
        backup.write_text(original, encoding="utf-8")

        # Apply each change in order
        text = original
        for c in changes:
            text = frontmatter.edit_field(text, c["field"], c["value"])
        abs_path.write_text(text, encoding="utf-8")
        applied += 1

    reindex.incremental(db_path, vault_id=vault_id)
    return {"applied": applied, "skipped": skipped, "backup_ts": ts}
