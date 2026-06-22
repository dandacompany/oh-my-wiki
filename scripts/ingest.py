"""Wiki-mode ingest helpers: save raw sources, write wiki pages, update index/log."""
from __future__ import annotations

from pathlib import Path

from scripts import frontmatter, registry, slugify


def _resolve_path(root: Path, folder: str, base: str, ext: str) -> str:
    """Return non-colliding relpath under root/folder with given base + ext."""
    candidate = base
    n = 2
    while (root / folder / f"{candidate}.{ext}").exists():
        candidate = f"{base}-{n}"
        n += 1
    return f"{folder}/{candidate}.{ext}"


def save_raw(
    db_path: Path,
    *,
    vault_id: int,
    content: str,
    ext: str,
    title: str,
    date_str: str,
) -> str:
    """Save a raw source under raw/<date>-<slug>.<ext>. Returns relpath."""
    root = registry.get_vault_root(db_path, vault_id)
    base = f"{date_str}-{slugify.slugify(title)}"
    relpath = _resolve_path(root, "raw", base, ext)
    abs_path = root / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return relpath


def save_raw_pdf(
    db_path: Path,
    *,
    vault_id: int,
    pdf_bytes: bytes,
    title: str,
    date_str: str,
) -> tuple[str, str]:
    """Save the original PDF bytes AND extract text. Returns (relpath, extracted_text)."""
    from pypdf import PdfReader
    from io import BytesIO

    root = registry.get_vault_root(db_path, vault_id)
    base = f"{date_str}-{slugify.slugify(title)}"
    relpath = _resolve_path(root, "raw", base, "pdf")
    abs_path = root / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(pdf_bytes)

    reader = PdfReader(BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    extracted = "\n\n".join(parts).strip()
    return relpath, extracted


WIKI_LAYERS = {
    "summaries":   "summary",
    "entities":    "entity",
    "concepts":    "concept",
    "comparisons": "comparison",
    "syntheses":   "synthesis",
}


def write_wiki_page(
    db_path: Path,
    *,
    vault_id: int,
    layer: str,
    title: str,
    body: str,
    tags: list[str],
    date_str: str,
    summary: str | None = None,
    status: str = "processed",
) -> str:
    """Write wiki/<layer>/<slug>.md with required frontmatter. Returns relpath."""
    if layer not in WIKI_LAYERS:
        raise ValueError(f"unknown wiki layer: {layer!r} (valid: {sorted(WIKI_LAYERS)})")
    root = registry.get_vault_root(db_path, vault_id)
    base = slugify.slugify(title)
    relpath = _resolve_path(root, f"wiki/{layer}", base, "md")
    type_ = WIKI_LAYERS[layer]
    meta: dict = {
        "title": title,
        "date": date_str,
        "type": type_,
        "tags": list(tags),
        "status": status,
    }
    if summary:
        meta["summary"] = summary
    abs_path = root / relpath
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(frontmatter.dump(meta, body), encoding="utf-8")
    return relpath


SECTION_BY_LAYER = {
    "summaries":   "Summaries",
    "entities":    "Entities",
    "concepts":    "Concepts",
    "comparisons": "Comparisons",
    "syntheses":   "Syntheses",
}


def _ensure_section(text: str, section: str) -> str:
    """Return text with `## {section}` present (appended at end if missing)."""
    header = f"## {section}"
    if header in text:
        return text
    suffix = "" if text.endswith("\n") else "\n"
    return text + suffix + "\n" + header + "\n"


def _insert_under_section(text: str, section: str, line: str) -> str:
    """Insert `line` under `## {section}`. Idempotent (no duplicate)."""
    header = f"## {section}"
    if line in text:
        return text  # already present
    lines = text.split("\n")
    out: list[str] = []
    inserted = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if not inserted and lines[i].strip() == header:
            # Skip past existing blank line; then place our line.
            j = i + 1
            while j < len(lines) and lines[j] == "":
                out.append(lines[j])
                j += 1
            out.append(line)
            i = j - 1
            inserted = True
        i += 1
    return "\n".join(out)


def update_index(
    db_path: Path,
    *,
    vault_id: int,
    entries: list[tuple[str, str, str]],
) -> None:
    """Add lines under section per entry. Entries: [(layer, slug, oneliner), ...]."""
    root = registry.get_vault_root(db_path, vault_id)
    index_path = root / "wiki" / "index.md"
    text = index_path.read_text(encoding="utf-8")
    for layer, slug, oneliner in entries:
        section = SECTION_BY_LAYER.get(layer)
        if section is None:
            raise ValueError(f"no index section for layer {layer!r}")
        text = _ensure_section(text, section)
        line = f"- [[{slug}]] — {oneliner}"
        text = _insert_under_section(text, section, line)
    index_path.write_text(text, encoding="utf-8")


def append_log(
    db_path: Path,
    *,
    vault_id: int,
    op: str,
    title: str,
    date_str: str,
) -> None:
    """Append `## [YYYY-MM-DD] <op> | <title>` to wiki/log.md."""
    root = registry.get_vault_root(db_path, vault_id)
    log_path = root / "wiki" / "log.md"
    text = log_path.read_text(encoding="utf-8")
    line = f"## [{date_str}] {op} | {title}\n"
    suffix = "" if text.endswith("\n") else "\n"
    log_path.write_text(text + suffix + line, encoding="utf-8")
