"""Deterministic export of a vault slice (by tag/type/visibility) to a
self-contained Markdown directory or zip, plus an EXPORT_MANIFEST.md listing
exported pages and dangling (out-of-slice) links. Writes ONLY under the given
out path; refuses to write inside the vault root. Never mutates the vault."""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from scripts import links, registry


class ExportError(Exception):
    """Raised on an unsafe or invalid export request."""


def _selected(db_path: Path, *, vault_id: int, tag, type_, visibility) -> list[str]:
    rows = registry.list_notes_faceted(
        db_path, vault_id=vault_id, tag=tag, type_=type_, visibility=visibility)
    return [r["relpath"] for r in rows]


def _dangling(db_path: Path, *, vault_id: int, exported: set[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for rel in sorted(exported):
        for link in links.outbound(db_path, vault_id, rel):
            target = link.get("dst_relpath")
            if target in exported:
                continue  # in-slice → fine
            key = (rel, link["dst_slug"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"from": rel, "slug": link["dst_slug"],
                        "dst_relpath": target})
    return out


def _write_manifest(base: Path, exported: list[str], dangling: list[dict]) -> None:
    lines = ["# Export manifest", "", f"## Exported pages ({len(exported)})", ""]
    lines += [f"- {r}" for r in exported]
    lines += ["", f"## Dangling links ({len(dangling)}) — targets outside this slice", ""]
    lines += [f"- `{d['from']}` → [[{d['slug']}]]" for d in dangling] or ["(none)"]
    (base / "EXPORT_MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export(db_path: Path, *, vault_id: int, out_dir: str | None = None,
           zip_path: str | None = None, tag=None, type_=None, visibility=None) -> dict:
    if not out_dir and not zip_path:
        raise ExportError("provide out_dir or zip_path")
    root = registry.get_vault_root(db_path, vault_id).resolve()
    for p in (out_dir, zip_path):
        if p and (Path(p).resolve() == root or root in Path(p).resolve().parents):
            raise ExportError(f"refusing to write inside the vault root: {p}")

    exported = _selected(db_path, vault_id=vault_id, tag=tag, type_=type_,
                         visibility=visibility)
    exported_set = set(exported)
    dangling = _dangling(db_path, vault_id=vault_id, exported=exported_set)

    staging = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    staging.mkdir(parents=True, exist_ok=True)
    for rel in exported:
        src = root / rel
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")  # verbatim
    _write_manifest(staging, exported, dangling)

    out = out_dir
    if zip_path:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(staging.rglob("*")):
                if f.is_file():
                    z.write(f, str(f.relative_to(staging)))
        out = zip_path
        if not out_dir:
            shutil.rmtree(staging, ignore_errors=True)
    return {"exported": exported, "dangling": dangling, "out": out}
