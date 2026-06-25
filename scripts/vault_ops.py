"""Orchestration for omw vault subcommands: filesystem moves, trash, and JSON
card assembly. Pure functions that take a registry db path; they raise
registry.VaultError on invalid operations. The registry module owns vaults-table
row mutations; this module owns filesystem + presentation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts import registry


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
