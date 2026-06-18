"""omw view — open the vault / a page / search in the configured viewer."""
from __future__ import annotations

import sys
from pathlib import Path

from scripts import config, registry, viewers
from scripts.paths import registry_path
from scripts.viewers.base import VaultRef, launch


class PageNotFound(Exception):
    def __init__(self, page: str, candidates: list[str]):
        super().__init__(page)
        self.page = page
        self.candidates = candidates


def pick_viewer_name(cfg: dict, override: str | None) -> str:
    if override:
        return override
    return (cfg.get("viewer") or {}).get("default") or "obsidian"


def viewer_vault_name(cfg: dict, viewer_name: str, root: Path) -> str:
    section = (cfg.get("viewer") or {}).get(viewer_name) or {}
    key = "graph_name" if viewer_name == "logseq" else "vault_name"
    return section.get(key) or root.name


def resolve_page(note_rows, root: Path, page: str) -> str:
    """Resolve <page> (relpath or slug/stem) to a vault relpath. note_rows: iterable of {'relpath'}."""
    if (root / page).is_file():
        return page
    relpaths = [r["relpath"] for r in note_rows]
    if page in relpaths:
        return page
    stem_hits = [rp for rp in relpaths if Path(rp).stem == page]
    if len(stem_hits) == 1:
        return stem_hits[0]
    candidates = stem_hits or [rp for rp in relpaths if page.lower() in rp.lower()][:5]
    raise PageNotFound(page, candidates)


def _resolve_vault(db_path, name: str | None):
    if name:
        return next((v for v in registry.list_vaults(db_path) if v["name"] == name), None)
    return registry.get_active(db_path)


def run(args) -> int:
    db = registry_path()
    if not db.exists():
        print("error: no registry; run `omw setup`", file=sys.stderr)
        return 1
    row = _resolve_vault(db, getattr(args, "vault", None))
    if row is None:
        print("error: no active vault; create one with `omw vault create` or pass --vault",
              file=sys.stderr)
        return 1

    cfg = config.load_config()
    viewer_name = pick_viewer_name(cfg, getattr(args, "viewer", None))
    try:
        viewer = viewers.get_viewer(viewer_name)
    except viewers.UnknownViewer as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    root = Path(row["path"])
    vault = VaultRef(root=root, name=viewer_vault_name(cfg, viewer_name, root))

    search = getattr(args, "search", None)
    page = getattr(args, "page", None)
    hint = None
    if search:
        uri = viewer.search(vault, search)
        if not viewer.supports_search:
            hint = f"{viewer_name}는 검색 URL 스킴이 없어 그래프만 엽니다. 앱에서 직접 검색하세요."
    elif page:
        try:
            relpath = resolve_page(registry.list_notes(db, vault_id=row["id"]), root, page)
        except PageNotFound as e:
            print(f"error: page not found: {page}", file=sys.stderr)
            if e.candidates:
                print("did you mean:\n  " + "\n  ".join(e.candidates), file=sys.stderr)
            return 1
        uri = viewer.open_page(vault, relpath)
    else:
        uri = viewer.open_vault(vault)

    if getattr(args, "print", False):
        print(uri)
    else:
        if not viewer.available():
            print(f"note: {viewer_name} may not be installed; opening URI anyway", file=sys.stderr)
        for line in viewer.preflight(vault):
            print(f"note: {line}" if not line.startswith(" ") else line, file=sys.stderr)
        try:
            launch(uri)
        except (FileNotFoundError, OSError):
            print(f"note: could not launch a URI handler for {viewer_name}; open this URI manually:",
                  file=sys.stderr)
        print(uri, file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    return 0
