"""Entry-router helper. Emits JSON the LLM dispatcher reads."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from scripts import paths, registry


def _legacy_vaults(db: Path) -> list[dict] | None:
    """Return vault dicts, or None if db is not a readable OMW registry."""
    try:
        return [{"name": v["name"], "path": v["path"]} for v in registry.list_vaults(db)]
    except Exception:
        return None


def status(db_path: Path) -> dict:
    db_path = Path(db_path)
    if not db_path.exists():
        # Already migrated once? Treat as clean.
        if (paths.omw_home() / "registry.db.migrated").exists():
            return {"vault_count": 0, "active": None, "needs": "setup", "confirm_target": False}
        # Detect a legacy registry to offer migration.
        for old in paths.legacy_registry_candidates():
            if old.exists():
                vaults = _legacy_vaults(old)
                if vaults is None:  # corrupt / non-OMW file → ignore this candidate
                    continue
                return {
                    "vault_count": 0,
                    "active": None,
                    "needs": "migrate",
                    "legacy_path": str(old),
                    "legacy_vault_count": len(vaults),
                    "vaults": vaults,
                    "confirm_target": False,
                }
        return {"vault_count": 0, "active": None, "needs": "setup", "confirm_target": False}
    vaults = registry.list_vaults(db_path)
    active = registry.get_active(db_path)
    if not vaults:
        needs = "setup"
    elif active is None:
        needs = "select"
    else:
        needs = "op"
    return {
        "vault_count": len(vaults),
        "active": {
            "name": active["name"],
            "path": active["path"],
            "type": active["type"],
            "mode": active["mode"],
        } if active else None,
        "needs": needs,
        "confirm_target": len(vaults) > 1,
        "vaults": [{"name": v["name"], "mode": v["mode"]} for v in vaults],
    }


def migrate(legacy: Path) -> int:
    """Copy a legacy registry to the global location; verify; mark legacy done.

    Returns the verified vault-row count. Leaves legacy intact on mismatch.
    """
    legacy = Path(legacy)
    src_count = len(registry.list_vaults(legacy))
    paths.ensure_home()
    dest = paths.registry_path()
    if dest.exists():
        raise RuntimeError(
            f"destination {dest} already exists; migrate only on a fresh install. "
            f"Back up or remove it first."
        )
    shutil.copy2(legacy, dest)
    dest_count = len(registry.list_vaults(dest))
    if dest_count != src_count:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"migration verification failed: {src_count} vaults in legacy, "
            f"{dest_count} copied. Legacy left intact at {legacy}."
        )
    (paths.omw_home() / "registry.db.migrated").touch()  # status() sentinel
    legacy.rename(legacy.parent / "registry.db.migrated")
    return dest_count


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wizard")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status")
    s.add_argument("--db", default=None)

    m = sub.add_parser("migrate")
    m.add_argument("--from", dest="legacy", required=True)

    args = p.parse_args(argv)

    if args.cmd == "status":
        db = Path(args.db) if args.db else paths.registry_path()
        # Compute status BEFORE any auto-init, so a pending migration is visible.
        result = status(db)
        # Only auto-init when there is nothing to migrate (fresh setup path).
        if result["needs"] != "migrate" and not db.exists():
            db.parent.mkdir(parents=True, exist_ok=True)
            registry.init_db(db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "migrate":
        n = migrate(Path(args.legacy))
        print(json.dumps({"migrated": True, "vault_count": n,
                          "registry": str(paths.registry_path())},
                         ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
