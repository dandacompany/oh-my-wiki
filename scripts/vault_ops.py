"""Orchestration for omw vault subcommands: filesystem moves, trash, and JSON
card assembly. Pure functions that take a registry db path; they raise
registry.VaultError on invalid operations. The registry module owns vaults-table
row mutations; this module owns filesystem + presentation."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from scripts import registry
from scripts.paths import omw_home

_VALID_MODES = {"memo", "wiki", "personal", "book", "business",
                "github-codebase", "website"}


def _require(db_path: Path, name: str) -> sqlite3.Row:
    row = registry.get_vault_by_name(db_path, name)
    if row is None:
        raise registry.VaultError(f"vault {name!r} not found")
    return row


def info(db_path: Path, name: str) -> dict:
    row = _require(db_path, name)
    counts = registry.note_layer_counts(db_path, row["id"])
    return {
        "name": row["name"],
        "path": row["path"],
        "type": row["type"],
        "mode": row["mode"],
        "is_active": bool(row["is_active"]),
        "archived": row["archived_at"] is not None,
        "archived_at": row["archived_at"],
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "note_counts": counts,
        "total_notes": sum(counts.values()),
    }


def current(db_path: Path) -> sqlite3.Row | None:
    return registry.get_active(db_path)


def rename(db_path: Path, old: str, new: str) -> dict:
    row = registry.rename_vault(db_path, old, new)
    return {"renamed": old, "to": row["name"]}


def move(db_path: Path, name: str, new_path: str) -> dict:
    row = _require(db_path, name)
    src = Path(row["path"])
    dst = Path(new_path).expanduser().resolve()
    if dst.exists():
        raise registry.VaultError(f"target path already exists: {dst}")
    # Update the registry first so a fs failure can't orphan a moved folder
    # under the old path; if the move fails we roll the path back.
    registry.update_path(db_path, name, dst)
    try:
        shutil.move(str(src), str(dst))
    except OSError as exc:
        registry.update_path(db_path, name, src)
        raise registry.VaultError(f"move failed: {exc}") from exc
    return {"moved": name, "from": str(src), "to": str(dst.resolve())}


def archive(db_path: Path, name: str) -> dict:
    _require(db_path, name)
    registry.set_archived(db_path, name, True)
    return {"archived": name}


def unarchive(db_path: Path, name: str) -> dict:
    _require(db_path, name)
    registry.set_archived(db_path, name, False)
    return {"unarchived": name}


def set_(db_path: Path, name: str, *, mode: str | None = None,
         config_pairs: list[str] | None = None) -> dict:
    row = _require(db_path, name)
    if mode is None and not config_pairs:
        raise registry.VaultError("nothing to set: pass --mode and/or --config k=v")
    if mode is not None and mode not in _VALID_MODES:
        raise registry.VaultError(
            f"invalid mode {mode!r}; choose one of {sorted(_VALID_MODES)}")
    config_json = None
    if config_pairs:
        existing = json.loads(row["config_json"]) if row["config_json"] else {}
        for pair in config_pairs:
            if "=" not in pair:
                raise registry.VaultError(f"bad --config {pair!r}; expected k=v")
            k, v = pair.split("=", 1)
            existing[k] = v
        config_json = json.dumps(existing, ensure_ascii=False)
    updated = registry.update_mode_config(db_path, name, mode=mode,
                                          config_json=config_json)
    return {"set": name, "mode": updated["mode"]}


def delete(db_path: Path, name: str, *, hard: bool, yes: bool, now_ts: str) -> dict:
    row = _require(db_path, name)
    if hard and not yes:
        raise registry.VaultError(
            "refusing hard delete without --yes (this is irreversible)")
    src = Path(row["path"])
    if hard:
        if src.exists():
            shutil.rmtree(src)
        registry.forget_vault(db_path, name)
        return {"deleted": name, "mode": "hard"}
    # soft: move folder into the trash dir, then forget
    trash_dir = omw_home() / ".trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / f"{now_ts}-{name}"
    if src.exists():
        shutil.move(str(src), str(dest))
    registry.forget_vault(db_path, name)
    return {"deleted": name, "mode": "soft", "trash": str(dest)}
